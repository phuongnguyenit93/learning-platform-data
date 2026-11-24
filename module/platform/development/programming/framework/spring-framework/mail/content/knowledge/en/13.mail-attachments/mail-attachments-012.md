# Preventing Arbitrary User Files from Becoming Attachments

An email-sending feature may allow users to upload documents and request the application to send them to others: invoices, support files, reports, or verification paperwork. In **Spring Framework Mail**, attaching a file to an email is straightforward with `MimeMessageHelper.addAttachment(...)`. However, this API only packages data into a MIME part; it **does not verify whether the file is safe, of the right type, owned by the user, or authorized to be sent to the recipient**.

If an application takes client-supplied uploaded files, filenames, content types, or paths directly and places them into an email, the attachment feature can become a delivery vector for malware, sensitive data, spoofed content, or oversized files. Because emails can be forwarded and stored across multiple mailboxes, mistakes at this step are much harder to retract than a file kept solely inside the application.

The core principle is **never turn an upload into an attachment immediately**. Route the file through an explicit validation and approval workflow, and attach only the verified data copy that matches the business purpose and recipient authorization.

## 1. Trust boundary from upload to email

An upload request can carry multiple client-controlled inputs:
- File bytes.
- Original filename sent by the browser.
- Extension such as `.pdf`, `.csv`, or `.docx`.
- `Content-Type` header of the multipart request.
- Declared size or actual size.
- Parameters such as document type, recipient, order code, or record ID.
- URLs or paths if the application lets users pick documents from elsewhere.

Those inputs **do not become trustworthy merely because they arrived via Spring MVC or were saved in a database**. Clients can forge headers, rename files, tamper with parameters, replay requests, or supply document IDs belonging to other users.

A safe workflow should include these steps:

```text
User uploads file
       |
       v
Enforce request limits and authenticate user
       |
       v
Store in quarantine / staging area
       |
       v
Run business-policy checks
       |
       +--> size, file type, signature, structure
       |
       +--> malware scan / CDR if needed
       |
       +--> ownership, tenant, data classification
       |
       v
Mark APPROVED or REJECTED
       |
       v
Verify permission to send to recipient
       |
       v
Create MimeMessage and addAttachment
       |
       v
JavaMailSender.send(...)
```

Not every application needs a complex quarantine subsystem. For an endpoint accepting only small invoice PDFs, the workflow can be leaner. Nevertheless, **decisions about file type, access rights, and safety checks must still occur before calling `addAttachment`**.

### 1.1. Distinguishing file states

Do not store just an `uploaded=true` column and treat every uploaded file as ready to send.

| State | Meaning | Allowed to attach? |
|---|---|---|
| `RECEIVED` | Server has received upload data. | Not yet. |
| `QUARANTINED` | File is awaiting inspection. | No. |
| `VALIDATING` | Checking format, structure, size, or permissions. | No. |
| `SCANNING` | Running malware scan or CDR processing. | No. |
| `APPROVED` | Passed mandatory policies for a specific purpose. | Yes, if sender and recipient are also authorized. |
| `REJECTED` | File violated policy or could not be verified. | No. |
| `EXPIRED` / `REVOKED` | File expired or was revoked. | No. |

`APPROVED` should be tied to **a specific intended use and content version**. A file approved as a profile avatar is not automatically approved as a financial attachment; a file modified after scanning must be re-inspected.

## 2. Dangerous assumptions to avoid

### 2.1. Do not trust the original filename

A client-supplied filename can look like:

```text
../../application.yml
invoice.pdf
invoice.pdf.exe
report.pdf%0d%0aBcc:attacker@example.net
C:\Users\Public\secret.txt
.hidden
very-long-name-....pdf
```

This name can contain paths, control characters, OS-specific separators, or misleading extensions. Never use that name directly as a storage path or email filename.

Instead:
- Generate a server-created storage key/ID.
- Generate the attachment name per business rules, e.g. `invoice-2026-001.pdf`.
- If the original name must be kept for display, store it separately as sanitized metadata.
- Strip CR/LF and control characters from display names.
- Never let a filename dictate access permissions or filesystem paths.

### 2.2. Do not trust the Content-Type sent by the browser

A client can send `Content-Type: application/pdf` for any arbitrary bytes. `MultipartFile.getContentType()` reflects request metadata, not proof that the actual data is a PDF.

An executable file can be renamed `report.pdf` and sent with header `application/pdf`. If the server only checks those two values, it can accept the wrong format.

Combine:
- business allowlist of document types;
- extension check as a secondary signal;
- format detection from bytes/signatures;
- an appropriate parser to confirm structure;
- malware scanning or content disarm and reconstruction when risk demands it.

No single check proves a file is completely safe.

### 2.3. Do not trust client-declared sizes

Use the actual size received by the server while enforcing limits at multiple layers:
- reverse proxy / API gateway;
- servlet multipart configuration;
- per-endpoint limits;
- per-file and total request limits;
- limits when building the MIME message;
- SMTP provider limits.

`MultipartFile.getSize()` is useful after a request arrives, yet proxy/container limits must block oversized payloads **before the application consumes excessive RAM or disk**.

### 2.4. Do not trust client-sent file IDs

If a request asks to send `fileId=123`, the server must verify that the file:
- exists;
- belongs to the right user/tenant or is validly shared;
- is in the `APPROVED` state;
- has not expired or been revoked;
- is authorized to be sent to the recipient for the current purpose.

An unguessable random ID does not replace authorization. Enforce object-level authorization on every file.

## 3. Building an allowlist by business purpose

Never write a blanket policy like "every file type except `.exe` is allowed". Instead, define **what document types a specific email needs**.

| Email flow | Accepted file types | Types to reject by default |
|---|---|---|
| Sending invoices | System-generated or verified PDF | Executables, scripts, HTML, unnecessary archives. |
| Data reports | CSV or XLSX per policy | Macro-enabled office files unless clearly needed, scripts, archives. |
| Support images | Verified or re-encoded JPEG/PNG | SVG/HTML without proper sanitization, executables, unknown files. |
| User records | Only business-specified, scanned types | Unlisted types, encrypted unscannable files if disallowed by policy. |

Allowlists should be expressed via server-side enums or configuration, never accepting an arbitrary MIME string from a request.

For example, a receipt-sending endpoint may **accept only PDFs**. Users must not be able to change a parameter to `application/zip` to send an archive through the same endpoint.

### 3.1. Rejecting unnecessary types

The following types typically require strict policies or should be rejected if not needed by business rules:
- executables, binary libraries, and installers;
- scripts and runnable files;
- HTML that may contain active content;
- SVG that may contain markup/active content depending on viewer handling;
- macro-enabled Office documents;
- nested archives or encrypted archives;
- unrecognized files or files a parser cannot verify.

Do not decide based on extension alone. For example, `.docx` is a ZIP container following Office Open XML format; a naive magic-byte check seeing only ZIP is insufficient to prove it is a valid Word document.

## 4. Format validation: multiple layers instead of one test

A file validation pipeline can combine:

1. **Business allowlist:** does this endpoint accept this file type?
2. **Name and extension:** does it match the requested type? This is only a secondary check.
3. **Content-Type detection:** detect format from bytes, e.g. using Apache Tika.
4. **Signature/magic bytes:** check expected format markers.
5. **Specialized parser/validator:** confirm the file structure is readable and not fundamentally malformed.
6. **Malware scanning:** scan via a managed engine or service.
7. **CDR/re-encoding:** for suitable file types, rebuild safe content from parsed data.
8. **Data policy:** verify the file contains information permitted to be sent via email.

Example with PDF:
- A file may start with `%PDF-` signature, yet checking only the prefix does not prove a complete PDF.
- Use a PDF parser to open and inspect its structure.
- Cap page count, size, object count, or features as needed.
- Scan for malware; if supported, use CDR to produce a clean PDF per policy.
- Attach **the bytes of the approved version**, never falling back to the raw initial upload.

### 4.1. Using Apache Tika to detect content type

Apache Tika can detect media types based on data and detection rules. Example:

```java
import org.apache.tika.Tika;

Tika tika = new Tika();
String detectedType = tika.detect(fileBytes);
```

Detection output is a helpful signal, not a verdict that the file is safe. Polyglot files, malformed structures, malicious payloads, or files crafted to fool detectors still require policy and specialized checks.

Never rely solely on:

```java
if ("application/pdf".equals(upload.getContentType())) {
    // Allow sending
}
```

because client headers can be forged.

### 4.2. Parsers must run with resource limits

Document parsers themselves can be exploited using specially crafted files or inputs that exhaust CPU/RAM. When processing untrusted files:
- enforce timeouts and memory limits;
- keep library versions patched;
- use low-privilege processes/containers if risk is high;
- limit size, page count, entry count, and nesting depth;
- disable arbitrary network or filesystem access in parsers;
- treat parser exceptions as validation failures, never accepting the file by default.

## 5. Malware scanning and quarantine zones

For user-uploaded documents, integrating antivirus or a scanning service may be required. Example flow:

```text
Upload bytes
    |
    v
Quarantine storage
    |
    v
Type / structure validation
    |
    v
Malware scanner
    |
    +--> CLEAN ----> APPROVED
    |
    +--> INFECTED -> REJECTED
    |
    +--> ERROR ----> QUARANTINED / RETRY / MANUAL REVIEW
```

Never treat a scanner connection failure as a "clean" result. When the scanner is unavailable, policy should **fail closed** for document types requiring scanning: hold the file in quarantine, retry, or ask the user to try again later.

An interface can decouple the application from the scanning provider:

```java
public interface MalwareScanner {
    ScanResult scan(byte[] content);
}

public enum ScanResult {
    CLEAN,
    INFECTED,
    UNAVAILABLE
}
```

This is an illustrative abstraction; real implementations can call ClamAV, a security service, or an internal scan gateway. Never ship a stub that always returns `CLEAN` in production.

If the system provides **Content Disarm and Reconstruction (CDR)**, it can rebuild the document from allowed content, strip unnecessary active elements, and pass the reconstructed copy through subsequent checks. CDR does not suit every file type and requires evaluating impacts on content and formatting.

### 5.1. Scan the exact version that will be sent

A design flaw is:
1. Scan uploaded file A.
2. File in storage is replaced with B.
3. Email sends B because the worker only reuses the file ID.

This is a form of TOCTOU (time-of-check to time-of-use). Mitigations:
- create immutable objects/versions after upload;
- store the checksum/hash of the scanned bytes;
- tie approval status to the object version/hash;
- when sending, read the exact approved version;
- if data changes, require re-scanning and re-approval.

For in-memory data, keep the exact validated byte array to build the attachment. If moving through object storage, pin the version or verify checksums so the worker fetches the exact content.

## 6. Size limits and archive bomb defense

A small file after decompression can expand into huge amounts of data. For instance, a ZIP bomb can contain nested compression layers or enormous entry counts. If an endpoint accepts archives, do not limit only the initial ZIP size.

Consider:
- maximum uploaded bytes;
- total size after decompression;
- maximum entry count;
- maximum archive nesting depth;
- abnormal compression ratios;
- extraction time limits;
- entry paths containing traversal such as `../../outside.txt`;
- encrypted archives preventing antivirus from scanning contents.

If business rules do not require ZIPs, rejecting archives is simpler. If needed, extract in a sandbox, never use entry names directly as destination paths, cap total bytes and entry counts, and scan every extracted item per policy.

### 6.1. Setting limits in Spring Boot

Example multipart limit configuration for small uploads:

```yaml
spring:
  servlet:
    multipart:
      max-file-size: 5MB
      max-request-size: 6MB
      file-size-threshold: 1MB
```

These numbers are examples only; choose based on business rules and infrastructure. `max-file-size` limits each file, while `max-request-size` limits the total multipart request. `file-size-threshold` affects the threshold between buffering multipart parts in memory versus temporary files depending on the servlet container.

Configure matching limits at your reverse proxy/API gateway because requests may be buffered before reaching Spring. Never rely solely on service-layer checks after the entire file has already been received.

## 7. Attachment filenames must be server-controlled

The original filename is untrusted metadata. In emails, filenames go into MIME headers such as `Content-Disposition`; control characters or abnormal values can cause parser errors, misrendering, or header injection if handled improperly.

A safe strategy:
- generate a new filename from the document type and business ID;
- use only the extension determined by policy/detection;
- cap length;
- strip CR, LF, NUL, and control characters;
- never put paths, usernames, email addresses, or sensitive data in filenames;
- never let the client choose the final filename directly.

Examples:

```text
invoice-ORD-2026-001.pdf
support-document-8f32a1.pdf
monthly-report-2026-11.csv
```

`MimeMessageHelper.addAttachment` takes the display filename separately from the byte resource. Pass the server-generated name, never a filesystem path.

Do not rely on `Paths.get(originalFilename).getFileName()` as your sole security measure. It may strip paths per OS rules, but it does not solve control characters, spoofed extensions, name collisions, or access controls.

## 8. Checking user and recipient permissions

A malware-free file can still be **unauthorized to send**.

Examples:
- User A guesses User B's file ID.
- A staff member sends one customer's invoice to another customer's email address.
- An internal document gets attached to a marketing email.
- A file was revoked, yet a queued send job still processes it.
- A user lacks permission to send another tenant's documents.

Before creating the attachment, verify:
1. Does the current actor have permission to read the document?
2. Does the document belong to the right tenant/customer/case/order?
3. Does the document state permit sending?
4. Is the recipient associated with the business entity and authorized to receive the file?
5. Is this data category permitted to be emailed under organizational policy?
6. Is the sender authorized to perform this action?

**Authorization must be enforced server-side per file and per recipient**, never based solely on request IDs or hidden UI buttons.

If an email goes to a user-entered address, verify permission to send the document to that address. A syntactically valid email address does not mean the recipient is authorized to receive the content.

## 9. Spring Boot example: sending only policy-approved PDFs

The following example illustrates an endpoint accepting **invoice PDFs**. Policy allows only PDFs, limits size, checks byte signatures, detects MIME, invokes a malware scanner and parser validator. The attachment filename is server-generated; original names and client `Content-Type` are never trusted as proof.

To focus on the workflow, the scanner and PDF validator are represented as interfaces. Production systems must provide real implementations and never default to skipping checks when the scanning service is unavailable.

### 9.1. Content detection dependency

You can add Apache Tika Core for media-type detection. Gradle example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.apache.tika:tika-core:<approved-version>'
}
```

`<approved-version>` is a placeholder; select an organization-approved Tika version compatible with your project's dependency policy. Do not copy placeholders into build files.

### 9.2. Approved attachment model

```java
package com.example.mail;

public record ApprovedAttachment(
    byte[] content,
    String filename,
    String contentType,
    String sha256
) {
    public ApprovedAttachment {
        content = content.clone();
    }

    @Override
    public byte[] content() {
        return content.clone();
    }
}
```

Cloning the byte array in the constructor and accessor prevents callers from mutating the array after approval. For large files, use immutable object storage versions and a stream abstraction instead of keeping all bytes in RAM.

### 9.3. Validation interfaces

```java
package com.example.mail;

public interface MalwareScanner {
    ScanResult scan(byte[] content);
}

public enum ScanResult {
    CLEAN,
    INFECTED,
    UNAVAILABLE
}
```

```java
package com.example.mail;

public interface PdfValidator {
    void validate(byte[] content);
}
```

`MalwareScanner` must call a real scan engine/service. `PdfValidator` must use a proper PDF parser to verify structure, bound resources, and reject malformed files. Never deploy an "always clean" or "always valid" stub to production.

### 9.4. Service validating PDF uploads

```java
package com.example.mail;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;

import org.apache.tika.Tika;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class PdfAttachmentPolicy {

    private static final int MAX_BYTES = 5 * 1024 * 1024;

    private final MalwareScanner malwareScanner;
    private final PdfValidator pdfValidator;
    private final Tika tika = new Tika();

    public PdfAttachmentPolicy(
            MalwareScanner malwareScanner,
            PdfValidator pdfValidator) {
        this.malwareScanner = malwareScanner;
        this.pdfValidator = pdfValidator;
    }

    public ApprovedAttachment approve(MultipartFile upload)
            throws IOException {

        if (upload == null || upload.isEmpty()) {
            throw new IllegalArgumentException("Missing PDF file");
        }

        // Check size before reading the whole upload into RAM.
        if (upload.getSize() > MAX_BYTES) {
            throw new IllegalArgumentException("File exceeds limit");
        }

        byte[] bytes = upload.getBytes();

        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("Invalid file size");
        }

        // PDF signature is one check layer, not proof of safety.
        if (!startsWithPdfSignature(bytes)) {
            throw new IllegalArgumentException("Content is not a PDF");
        }

        String detectedType = tika.detect(bytes);
        if (!"application/pdf".equals(detectedType)) {
            throw new IllegalArgumentException(
                "Detected format is not PDF"
            );
        }

        // Parser must verify structure and enforce resource limits.
        pdfValidator.validate(bytes);

        // Never accept scanner errors as clean results.
        ScanResult scanResult = malwareScanner.scan(bytes);
        if (scanResult != ScanResult.CLEAN) {
            throw new IllegalArgumentException(
                "File has not been confirmed safe"
            );
        }

        String hash = sha256(bytes);

        // Server-generated filename; never use originalFilename.
        String safeFilename =
            "document-" + UUID.randomUUID() + ".pdf";

        return new ApprovedAttachment(
            bytes,
            safeFilename,
            "application/pdf",
            hash
        );
    }

    private static boolean startsWithPdfSignature(byte[] bytes) {
        byte[] signature = "%PDF-".getBytes(StandardCharsets.US_ASCII);
        if (bytes.length < signature.length) {
            return false;
        }
        for (int i = 0; i < signature.length; i++) {
            if (bytes[i] != signature[i]) {
                return false;
            }
        }
        return true;
    }

    private static String sha256(byte[] bytes) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(bytes);
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
```

Limitations of this example:
- `MAX_BYTES` is an illustrative application threshold and must be lower than appropriate request/provider limits.
- `MultipartFile.getSize()` is checked before `getBytes()`, though proxy/container limits are still needed to block oversized requests early.
- Signatures and Tika only help identify file type; parsers and scanners remain essential.
- `UNAVAILABLE` from the scanner is rejected as unapproved.
- `sha256` binds the approval to the exact checked bytes; if persisted to storage, re-verify version/hash when sending.
- The original filename is never used as the attachment name.

### 9.5. Attaching only policy-approved objects

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class DocumentMailService {

    private final JavaMailSender mailSender;
    private final PdfAttachmentPolicy attachmentPolicy;
    private final DocumentAuthorization authorization;

    public DocumentMailService(
            JavaMailSender mailSender,
            PdfAttachmentPolicy attachmentPolicy,
            DocumentAuthorization authorization) {
        this.mailSender = mailSender;
        this.attachmentPolicy = attachmentPolicy;
        this.authorization = authorization;
    }

    public void sendPdf(
            String actorId,
            String recipient,
            String orderId,
            org.springframework.web.multipart.MultipartFile upload)
            throws Exception {

        // Check permission to send the document to the recipient for this order.
        authorization.requireCanSendOrderDocument(
            actorId, orderId, recipient
        );

        // Only returns data that passed policy.
        ApprovedAttachment attachment =
            attachmentPolicy.approve(upload);

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("documents@example.com");
        helper.setTo(recipient);
        helper.setSubject("Order document " + orderId);
        helper.setText(
            "The PDF document has been verified and attached."
        );

        helper.addAttachment(
            attachment.filename(),
            new ByteArrayResource(attachment.content()),
            attachment.contentType()
        );

        mailSender.send(message);
    }
}
```

`DocumentAuthorization` is an illustrative business interface. Implementations must check the relationship between actor, order, document, and recipient in a trusted database/service. Never rely on a client-supplied boolean like `isAuthorized=true`.

This code also assumes the scanner and parser operate synchronously. For large documents or slow scans, switch to an asynchronous pipeline: upload into quarantine, create a scan job, and permit sending only once the status is approved. In that case, the email worker receives **the ID of the approved attachment**, never a raw arbitrary upload again.

## 10. Asynchronous design with quarantine and approved storage

For systems with many users or large files, temporary objects can live in object storage:

```text
Upload API
    |
    v
Quarantine object (immutable version)
    |
    v
Validation / parser / malware scan
    |
    +--> REJECTED: retain metadata, delete/quarantine per retention
    |
    +--> APPROVED: store approved object reference + hash
                         |
                         v
                  Email request/outbox
                         |
                         v
                   Mail worker
                         |
                         +--> load exact approved version
                         +--> verify status/hash/authorization
                         +--> addAttachment
                         +--> send
```

Advantages:
- Avoids holding large files on the web request heap.
- Scanning can run in a separate worker with timeouts and retries.
- Preserves immutable versions and hashes.
- The mail worker only gets read access to approved objects as needed.
- Supports state tracking and auditing for every send.

Controls required:
- Never use client-chosen keys as storage paths.
- Never allow users direct access to quarantine objects.
- Only authorized mail workers can read approved objects.
- Verify the file has not been revoked or expired at send time.
- If the object version or hash differs from the scanned copy, do not attach it.
- Enforce retention and cleanup for rejected files, expired files, and temporary copies.
- Never set `public-read` on buckets just so mail workers can download files.

## 11. Do not automatically fetch user-supplied URLs

Some features let users enter a URL for the application to download a document and send an email. This introduces another risk: **Server-Side Request Forgery (SSRF)**.

A URL could point to:
- loopback or private network addresses;
- cloud metadata services;
- internal hostnames reachable only from the server;
- URLs redirecting to another host;
- huge endpoints or infinite streams;
- non-file resources such as HTML or live streams.

If business rules genuinely require accepting URLs:
1. Prefer an explicit allowlist of domains/hosts.
2. Allow only required schemes, typically HTTPS.
3. Resolve DNS and block private, loopback, link-local, multicast, and metadata IP ranges.
4. Re-verify targets after redirects; better yet, disable automatic redirects if unneeded.
5. Limit connect/read timeouts, downloaded bytes, redirect counts, and content types.
6. Never send internal credentials or user cookies to external hosts.
7. After downloading, still route bytes through the exact same validation/scan pipeline before attaching.

Never call `new URL(userInput).openStream()` or a default HTTP client to fetch an arbitrary URL and pass it straight to `addAttachment`.

## 12. Special format risks

### 12.1. HTML and SVG

HTML or SVG can contain markup, links, external resource references, or active content depending on how viewers render them. Do not allow them merely because they can be attached as files. When business rules need images, prefer raster PNG/JPEG decoded and re-encoded via an appropriate imaging library.

For uploaded images:
- verify actual format;
- limit width, height, and total pixel count;
- decode in a resource-bounded environment;
- re-encode into an allowed format;
- strip EXIF metadata if unneeded;
- never trust client-sent extensions or content types.

### 12.2. Office documents and macros

A `.docx` or `.xlsx` extension does not guarantee the absence of dangerous content. Office formats are container-based and can hold multiple components. If Office support is required:
- restrict allowed document types;
- reject macro-enabled formats unless clearly justified;
- inspect container structure and entries;
- scan contents after controlled extraction;
- consider converting to PDF in a sandbox if recipients only need read-only viewing.

### 12.3. Archives and ZIP Slip

When extracting, never concatenate entry names directly onto the target directory. An entry like `../../outside.txt` can escape the extraction folder if paths are not normalized and verified. Use an up-to-date archive library, verify normalized paths stay inside the destination directory, and cap entry counts and expanded sizes.

### 12.4. Encrypted or password-protected files

If a scanner cannot inspect the contents of a password-protected archive or PDF, never assume it is clean. Policy can:
- reject it;
- ask the user for an unencrypted copy via an appropriate channel;
- route it to a separate manual review workflow;
- or accept it only when an approved inspection method exists.

Never send encrypted files via email to evade antivirus scanning.

## 13. MIME attachment: the send API is not a security filter

Once a file is approved, Spring Mail only needs a resource and metadata:

```java
helper.addAttachment(
    approved.filename(),
    new ByteArrayResource(approved.content()),
    approved.contentType()
);
```

`addAttachment` does not automatically:
- scan for viruses;
- check recipient authorization;
- verify file type;
- validate PDF contents;
- sanitize filenames per business rules;
- verify the file belongs to the right user/tenant;
- enforce total size against application quotas.

That is why you must never pass `MultipartFile` or arbitrary names/Content-Types directly from a request into the helper without a policy layer in between.

### 13.1. Content-Disposition and filename

Attachments typically carry MIME headers:

```text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice-001.pdf"
Content-Transfer-Encoding: base64
```

Filenames should be server-generated. Avoid CR/LF, path separators, and control characters. Never place paths like `/var/app/uploads/invoice.pdf` into MIME headers; pass only the display filename.

### 13.2. Never use the client's Content-Type as the final Content-Type

Wrong:

```java
helper.addAttachment(
    upload.getOriginalFilename(),
    new ByteArrayResource(upload.getBytes()),
    upload.getContentType()
);
```

This trusts the client-supplied filename, MIME type, and bytes all at once. Instead, use the policy-verified object:

```java
helper.addAttachment(
    approved.filename(),
    new ByteArrayResource(approved.content()),
    approved.contentType()
);
```

Here `approved` is server-created data produced after validation. The filename and MIME type are policy outputs, not raw request metadata.

## 14. Common errors and solutions

| Symptom | Cause | Solution |
|---|---|---|
| Executable accepted as a PDF | Checked only extension or client MIME | Detection, signature, parser, and scan per allowlist. |
| Fake PDF attached | Checked only `%PDF-` | PDF parser, malware scan, and structural policy. |
| Filename contains path or CRLF | Used `getOriginalFilename()` directly | Generate filenames server-side, strip control characters. |
| User can send another tenant's file | Checked only that file ID exists | Object-level authorization and tenant scoping. |
| Scanner errored yet file was sent | Treated scanner error as clean | Fail closed, hold in quarantine, and retry/manual review. |
| File modified after scan | Scanned one version, sent another | Immutable objects/versions and hashes tied to approval. |
| Email exceeds size limits | No file or total MIME limits | Cap uploads, attachments, and concurrency; send links when needed. |
| Worker heap spikes sharply | Many large byte arrays/files at once | Queues, concurrency caps, storage streams, or spooling. |
| Extracted ZIP grows huge | Only capped initial archive size | Cap expanded bytes, entry count, depth, and duration. |
| Upload URL used to hit internal network | Arbitrary URL fetching | SSRF allowlist, DNS/IP checks, redirect policy, timeouts, byte caps. |
| Revoked file still sent | Checked status only at upload time | Re-verify approval/authorization at send time. |
| Malicious file scanned but not bound to send | Scan result not linked to hash/version | Send exact scanned bytes/version; check hash before attaching. |

## 15. Testing policies before permitting sends

Testing should focus on **allow versus reject** decisions and ensuring attachments use only approved data.

| Category | Example | Expected outcome |
|---|---|---|
| Valid file | Test-generated sample PDF | Passes detection, parser, and mocked CLEAN scanner. |
| Empty file | 0-byte upload | Rejected. |
| Oversized file | Larger than limit | Rejected before reading all bytes into RAM. |
| Spoofed MIME | EXE bytes with PDF header | Rejected. |
| Spoofed extension | PDF bytes with different extension | Handled per policy; never rely on original name. |
| Wrong signature | Missing PDF magic bytes | Rejected. |
| Corrupted PDF | Has prefix but parser fails | Rejected. |
| Malware | Scanner returns INFECTED | Rejected and state recorded appropriately. |
| Scanner unavailable | Scanner returns UNAVAILABLE/timeout | Not attached; held in quarantine/retried. |
| Dangerous filename | Path traversal, CR/LF, very long name | Output filename is server-generated and safe. |
| Unauthorized file | File belongs to another user/tenant | Rejected before creating email. |
| Unauthorized recipient | Recipient unrelated to record | Rejected. |
| Revoked file | Status REVOKED after upload | Not sent. |
| Object version changed | Hash differs from scanned copy | Not sent; requires re-scan. |
| Multiple attachments | Total size exceeds quota | Rejected or switched to secure link. |
| Archive bomb | Expanded size or entry count too high | Extraction aborted within limits. |

### 15.1. Unit tests for policies

You can mock the scanner and PDF validator to test business branches. Example:

```java
@Test
void rejectsFileWhenScannerIsUnavailable() throws Exception {
    when(scanner.scan(any()))
        .thenReturn(ScanResult.UNAVAILABLE);

    assertThatThrownBy(() -> policy.approve(validPdfUpload()))
        .isInstanceOf(IllegalArgumentException.class);
}
```

`validPdfUpload()` is a test fixture generating a PDF satisfying the test's validator. Never commit real PDFs containing customer data to the repository.

Another test should verify that a rejected file triggers no mail-sending call:

```java
@Test
void rejectedUploadDoesNotSendEmail() throws Exception {
    when(scanner.scan(any()))
        .thenReturn(ScanResult.INFECTED);

    assertThatThrownBy(() ->
        documentMailService.sendPdf(
            actorId, recipient, orderId, infectedUpload
        )
    ).isInstanceOf(IllegalArgumentException.class);

    verify(mailSender, never()).send(any(MimeMessage.class));
}
```

This test illustrates the idea; if a service creates `MimeMessage` before policy completes, verify `send(...)` was not called rather than asserting zero interactions. The cleanest design validates/approves first and only then constructs the MIME message.

### 15.2. Inspecting MIME in tests

For an approved attachment, build `MimeMessage` and verify:
- MIME multipart contains the attachment part;
- `Content-Type` matches the policy-chosen type;
- filename is the server-generated name;
- bytes extracted from the part match the approved input bytes;
- no other uploaded file or unintended parts exist.

Never print Base64 into logs. In tests, compare hashes or byte arrays directly.

## 16. Flow-based operational checklist

**Before accepting files:**
- Enable only file types genuinely required by business rules.
- Enforce request limits at proxy/container/Spring layers.
- Authenticate users and enforce upload quotas.
- Store files in staging/quarantine with server-generated keys.

**Before approval:**
- Verify expected file type, signatures, detection, and parsers.
- Scan for malware; treat scanner errors as unapproved.
- Cap archive extraction, expanded sizes, and processing time.
- Generate immutable hashes/versions and persist approval state.
- Apply CDR/re-encoding if policy requires.

**Before sending:**
- Verify actor, tenant, document, and recipient.
- Confirm status is still APPROVED and not expired or revoked.
- Read the exact scanned version/hash.
- Use server-generated filenames and Content-Types.
- Enforce total attachment size limits.
- Build separate MIME messages per recipient and business context.

**After sending:**
- Record event ID, attachment ID/version/hash, and send outcome.
- Never log file bytes, Base64, tokens, or sensitive contents.
- Enforce retention/cleanup for quarantine and temporary files.
- Handle bounces and delivery statuses if supported by the provider.
- Maintain a process to revoke access or documents if an incident is discovered.

## 17. Summary

**Preventing arbitrary user files from becoming attachments** is a data-control problem before sending email, not merely a MIME operation. `MimeMessageHelper.addAttachment(...)` will attach whatever resource the application provides; it does not verify origin, format, content, ownership, or file safety.

A trustworthy flow requires **business-scoped allowlists, upload limits, detection and parsers, malware scanning, quarantine/approval, authorization for both file and recipient, server-generated filenames, size controls, and sending the exact approved version**. For large files or asynchronous processing, persist immutable objects and bind scan results to hashes/versions. If a file cannot be verified against policy, never turn it into an attachment.
