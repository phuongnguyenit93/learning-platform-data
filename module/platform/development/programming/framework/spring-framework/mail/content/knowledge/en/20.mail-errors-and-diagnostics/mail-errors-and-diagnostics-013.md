# Creating a Safe Message Copy or MIME Dump for Investigation

When an email sent with Spring Framework Mail fails, developers often want to preserve the constructed message or export a MIME file for inspection. This helps uncover `Content-Type`, charset, boundary, attachment, inline image, and Jakarta Mail serialization issues. However, **a MIME dump can contain the entire email content**, from `To`/`Cc`/`Bcc` addresses to tokens, HTML, and attachments. Writing dumps straight to logs can trigger a data leak incident right in the middle of diagnostics.

This lesson explains how to **create a `MimeMessage` copy**, properly understand `MimeMessage.writeTo(...)`, prefer **safe MIME structural reports**, and collect raw dumps only when strictly necessary in controlled environments. The focus is keeping enough useful evidence without over-storing or spreading personal info, secrets, and email bodies.

## 1. Why Diagnose MIME?

An email notification passes through multiple layers:

```text
Business data
     |
     v
Template engine: HTML / plain text
     |
     v
MimeMessageHelper
     |
     v
MimeMessage: headers + MIME parts
     |
     v
JavaMailSender / Jakarta Mail
     |
     v
SMTP submission
     |
     v
Mail server / mailbox / mail client
```

Errors can appear at:

- **Data/template:** corrupted user-name diacritics, unescaped HTML, wrong URLs.
- **MIME composition:** missing `text/html`, wrong `multipart` nesting, mismatched CID, wrong attachment disposition.
- **Serialization:** unexpected encoded headers, boundaries, or `Content-Transfer-Encoding`.
- **SMTP:** connection failure, recipient rejection, oversized message, or timeout.
- **Delivery/client:** mail accepted by SMTP yet undelivered or rendered differently across mail clients.

Not every failure needs a dump. For example, `MailAuthenticationException` usually requires checking SMTP AUTH config; a raw MIME body will not fix wrong credentials.

## 2. Distinguishing Message Copy, Raw Dump, and Safe Summary

| Artifact type | What it holds | Risk | When to use |
|---|---|---|---|
| **Logical `MimeMessage` copy** | Message object with corresponding headers and body parts | Still holds PII/attachments | Want to inspect a separate object without mutating the original |
| **Raw MIME dump** | Bytes representing headers, MIME boundaries, body, encodings, and attachments | Very high | Byte-level investigation in restricted environments |
| **Safe MIME summary** | Base MIME type, part counts, disposition, reported sizes, CID/filename flags | Lower when allowlisted | Default production logging and diagnostics |

A `MimeMessage` copy is **not automatically anonymized**. Raw MIME is also not safe just because it looks like a text file or contains Base64 blocks. Conversely, a safe summary cannot prove every transmitted byte, yet usually suffices to spot common structural bugs.

### Priority Order

1. Start with notification ID, template version, exception class, and SMTP status.
2. Collect structural metadata rather than reading message content.
3. Reproduce using dummy data and an SMTP test server.
4. Only when evidence is still insufficient, consider real raw MIME with approval, encryption, access controls, and TTL.

## 3. What Does a MIME Message Actually Contain?

Example of a notification with text, HTML, an inline logo, and a PDF:

```text
MimeMessage
├── Headers
│   ├── From / To / Cc / Bcc
│   ├── Subject / Date / Message-ID
│   └── Content-Type / MIME-Version
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   └── image/png; Content-ID:<logo@example.org>
    └── application/pdf; disposition=attachment
```

This is an illustrative tree. Actual nesting depends on `MimeMessageHelper` and multipart mode configuration.

Inside raw MIME, there can be:

- Recipient addresses, including `Bcc` and internal mailboxes.
- Subjects containing customer names or case IDs.
- HTML/text bodies containing personal info.
- Password reset URLs, magic logins, or token-bearing unsubscribe links.
- Attachments containing PDFs/CSVs/images/Office files.
- File metadata, tracking queries, internal hosts, or transaction IDs.
- Custom headers added by the application.

`Content-Transfer-Encoding: base64` only exists to transport bytes over email; **it is not encryption**. Anyone reading the dump can decode and recover the files.

## 4. Choosing Investigation Data by Symptom

| Symptom | Question | Minimal data needed |
|---|---|---|
| Corrupted Vietnamese diacritics | Are part charsets and source data right? | Base MIME type, normalized charset, template version |
| Missing HTML version | Is there a `text/html` part? | MIME tree |
| CID image not showing | Does an inline part and `cid:` mapping exist? | Part count, anonymized CID presence/mapping |
| Missing attachment | Is there an attachment part and media type? | Disposition, type, reported size |
| SMTP rejected due to size | How large is the message? | Total size, SMTP reply code |
| Recipient rejected | At which stage did SMTP reject? | Transport/provider logs |
| Malformed header folding | How were header bytes serialized? | Raw MIME of test fixture |
| Wrong boundary | Was multipart serialization valid? | Raw MIME test capture |
| Email lands in spam | How are delivery/reputation? | Provider events, not raw body by default |

Never capture the entire email when you only need to know whether a PDF was attached to the message.

## 5. Creating a `MimeMessage` Copy with the Copy Constructor

Jakarta Mail provides a constructor accepting an existing `MimeMessage`:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

public MimeMessage createInspectionCopy(MimeMessage source)
        throws MessagingException {
    return new MimeMessage(source);
}
```

A copy supports inspecting a separate object, yet keep in mind:

- **Does not sanitize data:** the copy still holds headers, recipients, body, and attachments.
- **Does not prove byte identity:** object state may differ from final serialization.
- **Does not prove server acceptance:** the copy may have been created before transport ran.
- **Does not remove mutability risks:** avoid inspecting/copying while another thread modifies or sends the original message.
- **Not free:** copying may parse/serialize content and read resources, consuming CPU/memory.

### When to Take the Copy

```text
Build mail model and render template
             |
             v
Build MimeMessage
             |
             +---- Safe MIME summary: BEFORE_SEND
             |
             +---- Optional controlled copy
             |
             v
JavaMailSender.send(message)
             |
             v
Record SMTP outcome / exception
```

Record stage and timestamp on snapshots. If a copy is taken before calling `addAttachment(...)`, the copy will not reflect the attachment added later.

## 6. Copying an Object Is Not Capturing Wire Bytes

`MimeMessage` is an object that can be built incrementally. Details such as `Date`, `Message-ID`, MIME boundaries, and encodings may be finalized or altered during `saveChanges()` and serialization depending on the implementation.

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("notify@example.org");
helper.setTo("test@example.net");
helper.setSubject("Test message");
helper.setText("Plain text", "<p>HTML</p>");

MimeMessage snapshot = new MimeMessage(message);
// Snapshot reflects only the state at this moment.
```

If attachments are later added or the subject is modified on the original message, the snapshot no longer reflects the final message. If `writeTo(...)` on the copy triggers message preparation steps, resulting bytes can differ from the object right before the call.

When strict evidence is needed, record `snapshotStage`, template version, application build version, timestamp, and capture source. Never call a copied object byte-for-byte evidence from the SMTP server.

## 7. Generating Raw MIME via `writeTo()`

Jakarta Mail exposes a method to write a message to an `OutputStream`:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import java.io.ByteArrayOutputStream;
import java.io.IOException;

public byte[] serializeSyntheticMail(MimeMessage message)
        throws IOException, MessagingException {

    ByteArrayOutputStream output = new ByteArrayOutputStream();
    message.writeTo(output);
    return output.toByteArray();
}
```

**Use this example only with small messages and dummy data in test environments.** The method returns all MIME bytes: headers, body, and attachments. `ByteArrayOutputStream` and `toByteArray()` also allocate extra copies on the heap.

Do not do this:

```java
// Anti-pattern: raw MIME written to application stdout.
message.writeTo(System.out);
```

And do not do this:

```java
// Anti-pattern: turns the entire email into log content.
logger.debug("MIME={}", new String(
        rawMime, StandardCharsets.UTF_8));
```

Raw MIME can contain multiple parts and encodings rather than a uniform UTF-8 string. Forcing all bytes into a `String` can also distort byte-level diagnostics.

## 8. A MIME Dump Does Not Contain the Full SMTP Envelope

Distinguish:

```text
SMTP envelope:
  MAIL FROM:<bounce@example.org>
  RCPT TO:<recipient@example.net>

MIME message:
  From: Notification <notify@example.org>
  To: recipient@example.net
  Subject: ...
  Content-Type: multipart/alternative; ...
  [body]
```

`writeTo(...)` does not record all SMTP commands:

- Lacks all `MAIL FROM` and `RCPT TO` commands like a protocol transcript.
- Does not show per-recipient SMTP reply codes.
- Does not include `AUTH` and `STARTTLS` negotiations.
- Does not prove the server accepted `DATA`.
- Does not include headers added later by downstream relays.

If the incident is `550 relay denied` or recipient rejection, inspect transport/provider evidence rather than MIME dumps alone.

**`Bcc` needs special protection:** a pre-send object or copy can contain hidden recipients even though the recipient's mailbox does not display `Bcc`. Never infer from the mail client UI that a dump lacks `Bcc`.

## 9. Designing a Safe MIME Summary Instead

Instead of logging bodies, build a structural report:

```text
notificationId=mail-8a1...
stage=BEFORE_SEND
rootType=multipart/mixed
partCount=6

parts:
  root         multipart/mixed       size=unknown
  root.0       multipart/related     size=unknown
  root.0.0     multipart/alternative size=unknown
  root.0.0.0   text/plain            size=420
  root.0.0.1   text/html             size=1800
  root.0.1     image/png             size=8020 inline
  root.1       application/pdf       size=24200 attachment

hasAnyContentId=true
hasAnyFilename=true
```

This metadata helps confirm:

- Whether the message has text and HTML parts.
- Whether the inline part exists.
- Whether attachments were added with the right type/disposition.
- Whether the `multipart` structure makes sense.

No need to print `Subject`, `To`, `Cc`, `Bcc`, filenames, raw `Content-ID`s, or attachment bytes.

## 10. Fields Permitted via Allowlist

| Field | Recommendation | Note |
|---|---|---|
| App-generated notification ID | Yes | Contains no PII |
| Template key/version | Conditional | Do not embed user data in keys |
| Base MIME type | Yes | Strip parameters like `name`/`boundary` |
| Disposition | Yes | Normalize to `inline`/`attachment`/other |
| Reported size | Yes | `getSize()` may return -1 |
| Part count / nesting depth | Yes | Bound depth and part count |
| Has filename | Boolean | Never store real filenames |
| Has `Content-ID` | Boolean/count | Never store raw CIDs |
| Charset | Allowlist | `UTF-8`, `US-ASCII`, other |
| Transfer encoding | Allowlist | `base64`, `quoted-printable`, `7bit`, other |
| `Subject` and addresses | Not by default | Contains PII |
| Raw `Message-ID` | Restricted | May expose domains/identifiers |
| Custom headers | Not by default | May hold tokens/user IDs |
| Body/URL/attachments | Not by default | Sensitive data |

Do not collect all headers and scrub them with regexes. The safer approach is **building a fresh report containing exclusively allowlisted fields**.

## 11. Java Example: Traversing the MIME Tree Without Reading Body Text

The utility below gathers `path`, base MIME type, disposition, API-reported size, and filename/CID flags. It does not read `text/html`, `text/plain`, or attachment contents.

```java
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.ContentType;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.ParseException;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class SafeMimeInspector {

    private static final int MAX_DEPTH = 8;
    private static final int MAX_PARTS = 80;

    public record PartSummary(
            String path,
            String baseType,
            String disposition,
            int reportedSize,
            boolean hasFilename,
            boolean hasContentId
    ) {}

    public List<PartSummary> inspect(MimeMessage message)
            throws MessagingException, IOException {
        List<PartSummary> result = new ArrayList<>();
        visit(message, "root", 0, result);
        return List.copyOf(result);
    }

    private void visit(
            Part part,
            String path,
            int depth,
            List<PartSummary> result
    ) throws MessagingException, IOException {

        if (depth > MAX_DEPTH || result.size() >= MAX_PARTS) {
            return;
        }

        result.add(new PartSummary(
                path,
                safeBaseType(part.getContentType()),
                safeDisposition(part.getDisposition()),
                part.getSize(),
                part.getFileName() != null,
                part.getHeader("Content-ID") != null
        ));

        if (depth >= MAX_DEPTH || !part.isMimeType("multipart/*")) {
            return;
        }

        // Traverse Multipart containers only; do not read text/attachments.
        Object content = part.getContent();
        if (!(content instanceof Multipart multipart)) {
            return;
        }

        for (int i = 0;
             i < multipart.getCount() && result.size() < MAX_PARTS;
             i++) {
            visit(
                    multipart.getBodyPart(i),
                    path + "." + i,
                    depth + 1,
                    result
            );
        }
    }

    private static String safeBaseType(String raw) {
        try {
            String type = new ContentType(raw)
                    .getBaseType()
                    .toLowerCase(Locale.ROOT);
            return type.matches(
                    "[a-z0-9.+-]{1,64}/[a-z0-9.+-]{1,128}"
            ) ? type : "invalid-or-other";
        } catch (ParseException ex) {
            return "invalid-or-other";
        }
    }

    private static String safeDisposition(String value) {
        if (Part.INLINE.equalsIgnoreCase(value)) {
            return "inline";
        }
        if (Part.ATTACHMENT.equalsIgnoreCase(value)) {
            return "attachment";
        }
        return "unspecified-or-other";
    }
}
```

### Why Does This Utility Cap Part Count?

A MIME message can nest many `multipart` containers or thousands of parts. `MAX_DEPTH` and `MAX_PARTS` cap output size. `safeBaseType` keeps only normalized type/subtype; `safeDisposition` never logs arbitrary values. The `hasFilename` and `hasContentId` flags never expose real values.

**Technical limitation:** calling `getContent()` to traverse `multipart/*` can still cause the library to parse and read resources. This utility targets application-constructed messages that already have size bounds. For MIME received from untrusted sources, enforce total byte, time, CPU, and resource limits at the parser layer.

`Part.getSize()` can return `-1` if size is unknown. Represent it as "unknown"; never treat `-1` as a real byte count or sum it directly.

## 12. Adding Allowlisted Charset and Transfer Encoding

When diagnosing Unicode, classify charsets without logging raw headers:

```java
private static String safeCharset(String contentType) {
    try {
        String charset = new ContentType(contentType)
                .getParameter("charset");
        if (charset == null) {
            return "unspecified";
        }

        return switch (charset.toLowerCase(Locale.ROOT)) {
            case "utf-8" -> "utf-8";
            case "us-ascii" -> "us-ascii";
            case "iso-8859-1" -> "iso-8859-1";
            case "windows-1252" -> "windows-1252";
            default -> "other";
        };
    } catch (ParseException ex) {
        return "invalid";
    }
}
```

For `Content-Transfer-Encoding`, normalize to `base64`, `quoted-printable`, `7bit`, `8bit`, `binary`, or `other`. Never dump raw header strings from untrusted sources into logs.

A valid charset in MIME does not guarantee input data was uncorrupted. If the Java `String` was already garbled when read from a database or file, `MimeMessageHelper` cannot repair it.

## 13. Integrating into a Spring Mail Service

A service can record a summary tied to the notification ID right before sending:

```java
@Service
public class MailSubmissionService {

    private final JavaMailSender sender;
    private final SafeMimeInspector inspector;

    public MailSubmissionService(
            JavaMailSender sender,
            SafeMimeInspector inspector
    ) {
        this.sender = sender;
        this.inspector = inspector;
    }

    public void submit(UUID notificationId, MimeMessage message)
            throws MessagingException, IOException {

        var summary = inspector.inspect(message);

        // Save only allowlisted metadata with stage BEFORE_SEND.
        recordSafeDiagnostic(notificationId, "BEFORE_SEND", summary);

        sender.send(message);
    }
}
```

`recordSafeDiagnostic(...)` is an application-implemented method. `SafeMimeInspector` should be registered as a bean or instantiated appropriately. In production, collect summaries only via sampling, feature flags, or targeted investigation; bound retention and record sizes.

Never let diagnostic recording failures break critical mail-sending business logic unless policy mandates it. Never call this summary proof that the server received the mail.

## 14. Pre-Send MIME Snapshot Differs from Transport Evidence

| Source | What it can prove | What it cannot prove |
|---|---|---|
| Message object before `send` | Structure at capture time | That SMTP received those bytes |
| `writeTo(...)` | Serialization at invocation time | Full SMTP envelope |
| Test SMTP capture server | Bytes received by test server in test env | Production relay behaves identically |
| Provider response/events | Accepted/delivered outcomes per provider | Every mail client renders cleanly |
| Test mail client | Visual rendering in that client | Rendering in all other clients |

A pre-send snapshot can differ from a later capture due to `saveChanges`, `Message-ID`, `Date`, boundaries, or transport. Do not conclude a bug without knowing which stage each capture came from.

## 15. Why Stripping Headers with Regex Is Not Safe Enough

An unsafe approach:

```java
// Not complete MIME redaction.
String masked = rawText
        .replaceAll("(?im)^To:.*$", "To: [REDACTED]")
        .replaceAll("(?im)^Subject:.*$", "Subject: [REDACTED]");
```

It can miss:

- Multi-line header folding.
- `Cc`, `Bcc`, `Reply-To`, `Return-Path`, `Received`, and `X-*` headers.
- RFC 2047 encoded-words in subjects.
- Encoded parameters/filenames.
- Base64 or quoted-printable bodies.
- Token-bearing URLs in HTML/text.
- Attachments and file metadata.
- Nested `message/rfc822` emails.

**Regex redaction on raw strings is not complete MIME anonymization.** For routine reports, construct fresh diagnostic objects solely from allowlisted fields.

## 16. Why Do Attachments Require Special Care?

Attachments can be:

- Invoice PDFs containing names, addresses, transactions.
- CSVs containing customer lists.
- Office files holding authors, comments, and revision histories.
- Images carrying EXIF data or QR codes with tokens.
- ZIP archives containing many documents.

Removing `text/plain` and `text/html` while leaving attachments in a dump still exposes most sensitive data.

Metadata should stop at:

```text
mimeBaseType=application/pdf
disposition=attachment
hasFilename=true
reportedSize=25700
```

If file corruption is suspected, prefer a dummy sample file of the same type and size. When comparing real bytes is truly required, enforce access controls; never place raw attachments or guessable digests into general metrics.

## 17. Inspecting Inline Images and `Content-ID`

In HTML, inline images typically use `cid:`:

```html
<img src="cid:logo-demo@mail.example.org" alt="Logo">
```

In Spring Framework Mail:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("notify@example.org");
helper.setTo("tester@example.net");
helper.setSubject("Inline image test email");
helper.setText(
        "This is the text version.",
        "<p>Illustrative image:</p>"
                + "<img src=\"cid:logo-demo@mail.example.org\" alt=\"Logo\">"
);

helper.addInline(
        "logo-demo@mail.example.org",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
```

The value passed to `addInline` is the bare `Content-ID`, without `cid:` or angle brackets. Raw MIME may contain:

```text
Content-Type: image/png
Content-ID: <logo-demo@mail.example.org>
Content-Disposition: inline
```

If clients do not show the image, distinguish:

1. Does HTML have matching `src="cid:..."`?
2. Is there an inline part with the matching `Content-ID`?
3. Does MIME nesting involve `multipart/related`?
4. Are `Content-Type` and source bytes valid?
5. Does the mail client block or handle inline resources specially?

A safe summary can report the count of parts with CIDs and count of unmatched references **without logging actual CID values**. Detailed matching can happen in memory with dummy data. A `hasContentId=true` flag alone is insufficient to confirm HTML CIDs match.

## 18. Charset and `Content-Transfer-Encoding`

When Vietnamese emails have garbled diacritics, trace the entire path:

```text
File / Database / API bytes
          |
          v
Java String
          |
          v
Thymeleaf / template render
          |
          v
MimeMessageHelper charset
          |
          v
MIME Content-Type + transfer encoding
          |
          v
Mail client decoding
```

Example:

```java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setSubject("Payment confirmation");
helper.setText(
        "Thank you for your payment.",
        "<p>Thank you for your payment.</p>"
);
```

In a diagnostic summary, all that is needed may be:

```text
text/plain:
  charset=utf-8
  transferEncoding=quoted-printable

text/html:
  charset=utf-8
  transferEncoding=base64
```

This is illustrative; the library picks transfer encodings depending on content and serialization. Both parts are not required to use the exact encodings shown in the diagram.

If MIME declares UTF-8 yet source data was already decoded wrongly, changing headers will not fix it. Use a fixture containing a string like `Nguyễn Thị Ánh – 1.250.000 ₫` to test the whole pipeline without real email bodies.

## 19. Filenames and MIME Parameters

Attachments can be added as:

```java
helper.addAttachment(
        "sample-invoice.pdf",
        new ClassPathResource("mail/sample-invoice.pdf"),
        "application/pdf"
);
```

To investigate Unicode filename issues on a client:

- Verify `Content-Disposition: attachment` is present.
- Check `hasFilename` instead of logging the real filename.
- Confirm `Content-Type` and content encoding.
- Create a sample file `Hóa đơn thử nghiệm.pdf` to reproduce.
- If inspecting encoded parameters at the byte level is needed, use raw MIME from a test message.

Never log raw filenames from production. Filenames can contain customer names, identifiers, or case details.

## 20. Headers That Can Carry Sensitive Data

| Header | Risk |
|---|---|
| `From`, `To`, `Cc`, `Bcc` | Identities and recipient lists |
| `Subject` | Names, case IDs, private info |
| `Reply-To`, `Return-Path` | Internal addresses, bounce systems |
| `Message-ID` | May contain domains or internal correlation |
| `Received` | IPs, hostnames, and mail routing path |
| `Authentication-Results` | Domain info and auth checks |
| `DKIM-Signature` | Signing details and domain |
| `List-Unsubscribe` | URLs may contain tokens |
| Custom `X-*` | May contain tenant/user IDs or business metadata |

Do not include these headers in logs by default. If you need to know whether a header exists, record an allowlisted boolean.

### DKIM and Integrity

Modifying headers/bodies of a signed email can break DKIM signature validation. A copy whose recipients were replaced or content removed for anonymization **is no longer byte-level equivalent to the original**.

When investigating DKIM, separate:

- Access-controlled originals used for integrity verification, when authorized.
- Reproductions or anonymized copies used for discussion, not for proving an original signature is valid.

## 21. Combining with `MailSendException`

In a batch, Spring may throw `MailSendException`. API:

```java
Map<Object, Exception> failed = ex.getFailedMessages();
```

This map holds message objects reported as failed and their corresponding exceptions. Keys are **not email address strings by default**.

Avoid:

```java
// Do not log raw message objects.
logger.error("Failed message: {}", failedMessage);
```

Instead, correlate with notification IDs before sending:

```java
Map<Object, UUID> ids = new IdentityHashMap<>();

MimeMessage m1 = buildMessage(request1);
MimeMessage m2 = buildMessage(request2);

ids.put(m1, request1.notificationId());
ids.put(m2, request2.notificationId());

try {
    mailSender.send(m1, m2);
} catch (MailSendException ex) {
    for (var entry : ex.getFailedMessages().entrySet()) {
        UUID notificationId = ids.get(entry.getKey());
        String type =
                entry.getValue().getClass().getSimpleName();

        // Store correlation and exception class;
        // do not store raw MimeMessage.
        recordFailure(notificationId, type);
    }
}
```

`IdentityHashMap` matches **the exact object instance** within an active batch. Never store object identity in a database or use it as a retry key across restarts. Notification IDs must be durable business identifiers.

### When the Failed Map Is Empty

If `getFailedMessages()` is empty, you cannot conclude the batch succeeded. The error may have happened at connection setup or close without per-message mapping. Use the exception class, transport status, and batch notification ID list to continue investigating.

## 22. Do Not Arbitrarily Log Exception Messages

Exceptions from mail libraries or SMTP servers sometimes contain recipient addresses, hosts, senders, or other server-generated info. Never automatically forward full `ex.getMessage()` and stack traces to broadly accessible destinations.

A safer record:

```text
notificationId=4b26...
attempt=2
stage=SMTP_SUBMISSION
exceptionClass=MailSendException
rootFailureClass=SendFailedException
classification=RECIPIENT_REJECTION
outcome=FAILED
```

If detailed stack traces are needed, manage them in an authorized diagnostic channel with redaction and appropriate retention. Never attach raw MIME or recipient lists to application exception messages.

### MIME Errors Differ from SMTP Errors

| Exception / scenario | What to check |
|---|---|
| `MailPreparationException` | Templates, resources, MIME processing before send |
| `MailAuthenticationException` | Credentials, SMTP AUTH, TLS/provider policy |
| `MailSendException` | SMTP stage, replies, failed messages, transport outcome |
| `MessagingException` during construction | Headers, MIME parts, attachments, charset |
| Timeout after DATA | Acceptance unclear, provider events/reconciliation |
| Client rendering differences | MIME structure and client testing |

Raw MIME helps inspect how the message was constructed; it **does not prove** SMTP accepted it or recipients read it.

## 23. What Can a Diagnostic Record Look Like?

```json
{
  "notificationId": "b9a7...e1",
  "snapshotStage": "BEFORE_SEND",
  "templateKey": "order-confirmation",
  "templateVersion": "v7",
  "topLevelMimeType": "multipart/mixed",
  "partCount": 6,
  "hasTextPart": true,
  "hasHtmlPart": true,
  "inlinePartCount": 1,
  "attachmentCount": 1,
  "charsetCategory": "utf-8",
  "exceptionClass": "MailSendException",
  "outcome": "UNKNOWN"
}
```

This is an illustrative schema. Actual fields should be constructed from normalized values rather than copying raw headers. Use a non-PII `notificationId` and restrict read permissions per policy.

Never allow free-form fields like `debugNotes` or `rawHeaders` that can ingest user content and bypass allowlist filters.

## 24. Raw Dumps in Production Require a Dedicated Process

If metadata and test messages have not explained the error, collecting raw data from production requires answering:

| Question | Requirement |
|---|---|
| **Purpose** | Which specific bug requires raw bytes? |
| **Approval** | Who is authorized to request and view the dump? |
| **Scope** | Which exact notification/attempt only? |
| **Data minimization** | Which bodies/attachments/headers can be stripped? |
| **Storage** | Isolated store with encryption at rest and in transit? |
| **Access** | Least privilege and download/access auditing? |
| **Retention** | TTL and deletion procedure for copies? |
| **Incident** | If a dump is accidentally shared, what is the incident response process? |

Never download raw MIME onto personal laptops or share `.eml` files in chat or public tickets for convenience. Use a controlled diagnostic store and post anonymized conclusions in tickets.

## 25. Memory Limits and Capture Sizing

An email with a 25 MB attachment can cause far more than 25 MB of memory pressure when:

1. The message or resources are constructed and held on the heap.
2. `ByteArrayOutputStream` expands its internal buffer.
3. `toByteArray()` allocates a fresh copy.
4. Converting bytes to `String` or JSON creates additional allocations.
5. Multiple workers capture concurrently.

Safeguards:

- Never enable raw capture for all emails.
- Cap total bytes, duration, and capture counts.
- Cap part counts and nesting depth.
- If raw capture is permitted, prefer streaming into encrypted, access-controlled storage rather than logging.
- Never automatically capture real attachments when metadata suffices.
- Mark `TRUNCATED` if aborted mid-way; do not mislead readers into thinking the original email had broken MIME.

Calling `Arrays.fill(bytes, (byte) 0)` on one array does not prove all copies in the JVM were wiped. Stronger protection is **minimizing or avoiding sensitive raw byte creation upfront**.

## 26. Hashes and Checksums: Useful, Not Self-Securing

In test environments:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] hash = digest.digest(rawTestMime);
```

Hashes can tell whether two byte snapshots are identical. However:

- Two dumps may differ solely due to `Date`, `Message-ID`, or boundaries.
- A hash does not show where or why they differ.
- A hash does not prove the SMTP server received the message.
- Hashes of small/predictable content can be guessed via dictionary attacks.
- The hash of a redacted copy does not match the original's hash.

If correlating sensitive content is necessary, consider HMAC with managed keys and bounded retention; never put raw hashes of customer content into public metric labels.

## 27. Do Not Inspect and Send the Same Mutable Message Across Threads

`MimeMessage` is a mutable object. A dangerous pattern:

```text
Thread A: build MimeMessage
Thread B: message.writeTo(diagnosticStream)
Thread C: mailSender.send(message)
```

Serialization, `saveChanges()`, resource reads, and header updates can overlap, making snapshot timing unclear or altering failure behavior.

Best practices:

1. Have a single worker own building and sending the message.
2. Collect safe summaries in a clear sequence before sending.
3. Create copies only in controlled steps without concurrent read/write.
4. Pass notification IDs and DTOs through queues rather than sharing mutable messages.
5. Attachments should use re-readable resources rather than sharing already-closed `InputStream`s.

## 28. Collection Levels by Environment

| Environment | Suggested policy |
|---|---|
| Unit tests | Raw MIME from dummy fixtures to test headers/encodings |
| Integration tests | SMTP capture server and test accounts |
| Local development | Dummy data, file limits, and short retention |
| Staging | Safe summary by default; scoped raw tests |
| Production | Minimal metadata; real raw captures require formal process |
| Support tickets | Anonymized conclusions; never attach real raw dumps |

GreenMail, Mailpit, and MailHog are useful for receiving test messages, inspecting raw MIME, or checking structure. Never let an uncontrolled SMTP test server receive production emails containing PII.

### Reproduction Workflow Using a Test Server

```text
Pick the bug to reproduce
       |
       v
Create fixture with dummy names/addresses/tokens
       |
       v
Build MimeMessage through the exact same code path
       |
       v
JavaMailSender sends to SMTP test server
       |
       v
Capture raw MIME of dummy data
       |
       v
Analyze MIME headers/parts/encoding
       |
       v
Fix code and re-run test send
```

## 29. Scenario: Outlook Does Not Display the PDF

A user reports receiving an invoice email, yet Outlook shows no attachment.

**Investigation:**

1. Look up the notification ID and check SMTP status.
2. Read the safe summary to verify `application/pdf` part, `disposition=attachment`, and `hasFilename=true`.
3. Rebuild using a sample PDF of the same type and size.
4. Send to test Outlook and test Gmail accounts.
5. If byte-level analysis is still needed, inspect raw capture of the test message.
6. Collect raw production data only with clear justification and proper authorization.

Ticket conclusions can read "template version X used the wrong disposition", without mentioning customer names or real filenames.

## 30. Scenario: Email Has Corrupted Vietnamese Diacritics

Fixture:

```text
Test recipient: Nguyễn Thị Ánh
Amount: 1.250.000 ₫
Message: Cảm ơn bạn – hẹn gặp lại.
```

Check:

- Is the Java `String` from the database/API already right?
- What string does the template render?
- Do `text/plain` and `text/html` declare the right charset?
- Is MIME transfer encoding working?
- Do different clients render it differently?

If the fixture reproduces the bug, no real email body is needed to fix the encoding.

## 31. Scenario: SMTP Timeout After DATA

The worker finished transmitting the message yet lost the connection before receiving the final reply. Even with full raw MIME, you still cannot tell for sure whether the server accepted the message.

This is an **ambiguous transport outcome**, not necessarily a MIME bug:

- Do not immediately retry the entire batch assuming unsent.
- Record `UNKNOWN` and attempt metadata.
- Check provider events/logs if available.
- Apply reconciliation or duplicate-aware retry policies.

Raw MIME shows how content was built; it cannot substitute for SMTP acceptance proof.

## 32. Scenario: Suspected Header Injection or Token Leak

If user input is suspected of influencing headers:

- Never post real raw headers to public issues.
- Build a fixture with CR/LF, Unicode characters, and unusual strings to reproduce.
- Check validation/escaping when setting headers.
- Cross-check transport outcomes if you need to know what was actually transmitted.
- If secrets/tokens may have leaked, execute incident response and revoke tokens per policy.

Never turn a security bug into a second data leak by sharing dumps.

## 33. Testing Diagnostic Utilities

Test using **dummy** sensitive data, never real accounts:

| Test input | Expected in safe summary |
|---|---|
| Subject with dummy secret code | Code does not appear |
| `To`/`Cc`/`Bcc` with sample emails | Real addresses do not appear |
| HTML with dummy magic link | URL/token does not appear |
| Filename containing a personal name | Only `hasFilename=true` |
| Attachment with sample data | No Base64 or bytes appear |
| `Content-Type` containing `name` parameter | Outputs base type only |
| Header with abnormal CR/LF | Raw value is not logged |
| Deeply nested MIME | Stops at `MAX_DEPTH` |
| Too many body parts | Stops at `MAX_PARTS` |
| `getSize() == -1` | Represented as unknown |
| MIME parsing throws exception | Records safe error category only |

For externally received MIME, add byte, time, and resource quotas at the parser layer; capping record counts after parsing is insufficient to prevent resource exhaustion.

## 34. Anti-Pattern: Writing `.eml` Files on Exception

Example never to deploy in production:

```java
try {
    mailSender.send(message);
} catch (MailException ex) {
    message.writeTo(new FileOutputStream(
            "last-failed-email.eml"));
    throw ex;
}
```

Risks:

- Fixed filename gets overwritten or races across concurrent workers.
- Contents write PII/attachments/tokens onto disks without access management.
- No TTL, audit, or encryption.
- Failures writing the dump obscure the original SMTP error.
- Post-error dumps may differ from what the server received.

Instead: log notification ID and exception class, capture a bounded safe summary, and request raw data only through a dedicated diagnostic channel when truly needed.

## 35. Anti-Pattern: Replaying Real Raw Messages

Never take a production `.eml` file and resend it just to reproduce:

- May send duplicate emails to customers.
- May send tokens or personal content to inappropriate addresses.
- May trigger links/tracking or other workflows.
- Copies with replaced recipients, subjects, or attachments are no longer byte-identical to the original.

Create dummy fixtures, swap recipients/envelopes for test mailboxes, and confirm no real tokens remain. Clearly label the artifact as a **reproduction message** rather than byte-identical evidence.

## 36. Technique Selection Table by Need

| Need | Preferred approach | Unnecessary action |
|---|---|---|
| Confirm HTML part exists | MIME structure summary | Dump body |
| Check attachments | Part type/disposition/count | Log filenames |
| Check inline images | Anonymized CID count/mapping | Log real CIDs |
| Check charset | Allowlist + Unicode fixture | Dump customer emails |
| Diagnose SMTP AUTH | Config/provider replies | Read MIME content |
| Diagnose RCPT rejection | SMTP transport evidence | Rely on `To` header |
| Diagnose boundaries | Raw MIME test capture | Publish raw production |
| Diagnose attachment bytes | Test sample or restricted diff | Log real PDFs |
| Share with support | Safe summary | Attach raw `.eml` |
| Track duplicate sends | Notification ID/attempt/provider events | Treat `Message-ID` as strict dedup |

## 37. Implementation Checklist

### Message Creation Stage

- [ ] Have notification ID and template version.
- [ ] Notification ID contains no personal data.
- [ ] Inspector collects allowlisted fields with part/depth caps.
- [ ] One thread/worker owns the mutable message per stage.
- [ ] Never log `Subject`, recipients, or bodies.

### Sending Stage

- [ ] Never call `writeTo(System.out)`.
- [ ] Separate MIME preparation errors from SMTP transport errors.
- [ ] Attach stage/timestamp to snapshots.
- [ ] Never treat pre-send dumps as SMTP wire captures.
- [ ] Never log unsanitized exception messages.

### Investigation Stage

- [ ] Attempted reproduction with dummy fixtures first.
- [ ] If real raw data is needed, explicit approval and scope exist.
- [ ] Encryption, least privilege, audit, and TTL are enforced.
- [ ] Never rely on regexes over raw MIME as the sole anonymization control.
- [ ] Never paste raw dumps into shared chats/tickets.
- [ ] Never use raw MIME to conclude Inbox delivery.

### Post-Investigation

- [ ] Conclusions contain no sensitive data.
- [ ] Delete artifacts per retention policy.
- [ ] Revoke temporary sharing links.
- [ ] Keep dummy fixtures for regression tests.

## 38. Common Mistakes

| Mistake | Consequence | Remediation |
|---|---|---|
| `writeTo(System.out)` | Leaks raw email into logs | Safe MIME summary |
| Treating copy constructor as anonymization | Still leaks body/attachments | Protect copies like real messages |
| Treating a copy as exact wire evidence | Wrong stage/bytes | Record stage and capture source |
| Stripping `To`/`Subject` via regex | Misses `Bcc`, tokens, encoded bodies | Build allowlisted reports |
| Treating Base64 as encryption | Content trivially decoded | Access controls and encryption |
| Logging full `Content-Type` | Parameters may carry sensitive info | Extract base type only |
| Logging real filenames/CIDs | Leaks names/identifiers | Booleans/counts |
| Unbounded dumps | OOM/disk exhaustion | Byte and scope caps |
| Copying concurrently with `send` | Inconsistent snapshots | Clear ownership and stages |
| Replaying production emails | Duplicate sends / token leaks | Dummy test fixtures |
| Treating dumps as delivery proof | Misreported status | Provider events |
| Storing dumps indefinitely | Amplifies data exposure risk | TTL/audit/deletion |
| Truncating without note | Misleads into thinking original MIME broke | Label `TRUNCATED` |
| Putting content hashes into metrics | Cardinality and privacy risks | Correlation IDs |

## 39. Scenario Exercises

### A. Safe Summary Shows Inline Image Has a `Content-ID`

Does that prove HTML references the exact right CID?

**Answer:** not yet. The summary only shows the header exists; you must verify the `cid:` URI mapping against `Content-ID` in an authorized environment, along with the `multipart/related` structure.

### B. Charset Is UTF-8 Yet Person Names Still Look Garbled

Do we definitely need real raw MIME?

**Answer:** not necessarily. Data may already have been corrupted from files or databases before building the message. Reproduce with a diacritic test string and check the whole pipeline.

### C. Raw MIME Contains a `To` Address

Can we assert SMTP accepted `RCPT TO` for that address?

**Answer:** no. MIME headers are not an SMTP envelope/reply transcript. Provider or transport evidence is required.

### D. A Developer Stripped `To`/`Subject` Using Regex

Can the `.eml` file be shared on a public issue?

**Answer:** no. Folded headers, `Bcc`, body tokens, Base64, filenames, and attachments can still leak data.

### E. SMTP Timeout After DATA

We have the raw bytes; can we retry immediately?

**Answer:** acceptance cannot be inferred from a dump. Mark the outcome ambiguous and reconcile per policy.

### F. A Copy Was Taken Before Adding the PDF

Does a copy lacking the attachment prove the sent message omitted the PDF?

**Answer:** no. Check the copy's stage; the attachment may have been added after the snapshot timestamp.

## 40. Conclusion

**`MimeMessage` copies** and **raw MIME dumps** are useful investigative tools in Spring Framework Mail, yet they can hold entire email contents and personal data. `new MimeMessage(original)` creates only a separate object, without anonymizing anything. `MimeMessage.writeTo(...)` writes message bytes at serialization time, is not a safe summary, and omits the full SMTP envelope.

The right approach starts with **notification ID, exception class, template version, transport outcome, and a normalized MIME structure summary**. When byte-level inspection is needed, prefer reproducing with dummy data on an SMTP test server. Only when production data is genuinely required should raw captures happen under an approved, scoped, encrypted, access-controlled, audited, and TTL-bound process.

By cleanly separating **message object**, **serialized snapshot**, **SMTP evidence**, and **diagnostic metadata**, development teams can explain MIME, charset, inline image, attachment, and header issues accurately without turning debugging into a new source of data leaks.
