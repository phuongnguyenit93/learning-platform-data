# MailParseException When Creating an Invalid Message

## 1. Context: Creating a Successful Email Is Not Just Creating a Text String

In **Spring Framework Mail**, an email can consist of a sender, recipients, a subject, `text/plain` content, HTML, inline images, and attachments. To be sent over SMTP, these components must be represented in the **MIME (Multipurpose Internet Mail Extensions)** format and follow the rules of the Internet Message Format.

At a simple level, an application can send a `SimpleMailMessage`. When HTML, Unicode, multiple body parts, or attachments are needed, the application usually uses `JavaMailSender`, `MimeMessage`, and `MimeMessageHelper`.

~~~text
Application data
   |
   v
Validation / building the mail model
   |
   v
MimeMessageHelper / MimeMessage
   |
   v
MIME preparation and encoding
   |
   v
JavaMailSender.send(...)
   |
   v
SMTP server
~~~

The issue is that **errors can appear at many different stages**:

- Invalid input data, for example an email address missing the domain part.
- Headers of a message read from an external source are malformed.
- Raw MIME data is truncated or the multipart structure is inconsistent.
- The character set or `Content-Transfer-Encoding` of a MIME part is inappropriate.
- `MimeMessagePreparator` fails when setting recipients, content, or attachments.
- MIME is created successfully, but SMTP rejects it or the connection encounters an issue.

The exception name **`MailParseException`** easily leads readers to think that whenever any email information is wrong, Spring always throws this exception. In reality, it is mainly related to **being unable to parse mail message content** at the read/parse boundary, and must be distinguished from **content preparation** errors or **SMTP sending** errors.

**Key takeaway:** You must determine whether the failure occurs while *reading MIME*, *preparing MimeMessage*, or *submitting to SMTP* before choosing how to fix and retry. Do not treat every email creation error as a mail server connection error.

## 2. What Is MailParseException?

`org.springframework.mail.MailParseException` is an exception in the Spring Mail hierarchy indicating that a mail message **cannot be parsed** in the way Spring is attempting. It belongs to the `MailException` family (runtime exception).

A typical scenario is when the application receives an email in the form of **raw RFC 822/MIME bytes** from a file, message store, or another system, and then tries to convert that data into a `MimeMessage`.

Example flow:

~~~text
.eml file / raw MIME InputStream
              |
              v
JavaMailSender.createMimeMessage(InputStream)
              |
              +-- parsed into MimeMessage successfully
              |
              +-- error during parsing
                         |
                         v
                   MailParseException
~~~

With Spring `JavaMailSender`, the commonly seen API is:

~~~java
MimeMessage message = mailSender.createMimeMessage();
~~~

Creates an empty message for the application to populate. Alternatively:

~~~java
MimeMessage restored =
        mailSender.createMimeMessage(rawMimeInputStream);
~~~

The second approach must **read and parse existing MIME data**. If the raw content causes a parse error, `MailParseException` is the exception to look out for.

There is no rule that every malformed message leads to `MailParseException` immediately when the constructor runs. A MIME parser may accept some non-standard structures for compatibility with real-world emails; some errors only surface later when accessing headers/body parts or serializing. Therefore, it is necessary to inspect the exception chain, timing of the error, and input data.

## 3. Distinguishing Important Exceptions in Spring Mail

Spring provides several exception types to classify issues:

| Exception | Common nature | Stage to investigate |
|---|---|---|
| `MailParseException` | Unable to parse mail message | Reading raw MIME / creating message from existing data |
| `MailPreparationException` | Error executing message preparation work | `MimeMessagePreparator`, template, helper, or data |
| `MailAuthenticationException` | Failed to authenticate with the mail server | SMTP AUTH / credentials |
| `MailSendException` | Error sending message, possibly multiple messages or recipients | SMTP transport, server response, connection |
| `MailException` | General Spring Mail error family | Need to inspect subtype and root cause |

In Jakarta Mail, several other exceptions also frequently appear:

| Underlying exception | Example |
|---|---|
| `jakarta.mail.MessagingException` | Error preparing/reading MIME or operating on a message |
| `jakarta.mail.internet.AddressException` | Email address has invalid syntax |
| `jakarta.mail.internet.ParseException` | A MIME/header syntax not accepted by the parser |
| `java.io.IOException` | Error reading stream or resource while processing content |

**Do not equate MailParseException with AddressException.** A syntactically invalid recipient address can cause `AddressException` during `MimeMessageHelper.setTo(...)`; if that error happens inside a `MimeMessagePreparator` passed to `JavaMailSender.send(...)`, Spring may wrap it in `MailPreparationException`. The exact exception path depends on the API overload and when the error occurs.

### Three Easily Confused Scenarios

**Scenario A — Parsing existing MIME data**

~~~java
MimeMessage message = mailSender.createMimeMessage(inputStream);
~~~

Reads raw MIME from `inputStream`. If the library cannot parse it, investigate the source data, headers, boundaries, stream, and MIME parts.

**Scenario B — Creating a new message using helper**

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");
helper.setTo(recipient);
helper.setText(html, true);
~~~

When `recipient` or another parameter is invalid, `MimeMessageHelper` APIs can throw `MessagingException` or a related subtype. This is a **message construction** issue; do not assume by default it will always be `MailParseException`.

**Scenario C — Sending a message over SMTP**

~~~java
mailSender.send(message);
~~~

If the message was created validly but the SMTP server cannot be reached or rejects the request, investigate `MailSendException`, `MailAuthenticationException`, provider policy, and SMTP responses. Do not change the MIME parser when the cause is wrong credentials.

## 4. Understanding MIME Structure to Understand Parse Errors

A structurally valid raw MIME message typically has headers, a blank line, and then a body:

~~~mime
From: noreply@example.test
To: customer@example.test
Subject: Confirmation
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o, =C4=91=C6=A1n h=C3=A0ng =C4=91=C3=A3 x=C3=A1c nh=E1=BA=ADn.
~~~

The headers indicate that the body is UTF-8 `text/plain` represented using `quoted-printable`. The mail client/Jakarta Mail must interpret the relevant headers and then decode the body.

A message with an attachment may consist of MIME parts separated by a boundary:

~~~mime
From: noreply@example.test
To: customer@example.test
Subject: Receipt
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mail-boundary-123"

--mail-boundary-123
Content-Type: text/plain; charset=UTF-8

Your receipt is attached.
--mail-boundary-123
Content-Type: application/pdf; name="receipt.pdf"
Content-Disposition: attachment; filename="receipt.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQK...
--mail-boundary-123--
~~~

Elements that must match:

1. The boundary declared in `Content-Type` must correspond to the delimiters in the body.
2. Each MIME part has its own headers and content section.
3. There is a blank line separating headers from the body/part body.
4. Fields such as `Content-Type`, charset, and transfer encoding must accurately describe the data.
5. The message must be read completely, avoiding a stream cut off mid-way.

A raw message does not necessarily need every common header to be accepted by the parser; Jakarta Mail can accept some non-standard data. However, malformed headers/bodies can cause parsing to fail, cause a body part to be misinterpreted, or only trigger errors when the application accesses the content.

## 5. Common Causes of MailParseException

| Cause group | Symptom | What to check |
|---|---|---|
| Corrupted input stream or read failure | `IOException`, stream closed prematurely | File source, stream lifecycle, filesystem/network |
| Truncated raw MIME | Missing body section or closing boundary | Actual bytes read vs. source size |
| Non-standard header syntax | `Content-Type` or MIME parameters cannot be parsed | Raw headers, control characters, quotes |
| Inconsistent multipart boundary | Parts merged, missing part, or parse error | Boundary value and delimiter lines |
| Wrong `Content-Transfer-Encoding` | Body decode error or corrupted data | Base64, quoted-printable, raw bytes |
| Inappropriate charset | Corrupted Vietnamese diacritics in content | `Content-Type` charset, original byte encoding |
| Nested parts with unusual structure | Error appears while traversing body | `multipart/alternative`, `related`, `mixed` |
| Header data with unexpected CR/LF | Header folded/split into lines unintentionally | Header source and untrusted input |
| `.eml` file does not actually contain raw MIME | Parser encounters content in a different format | File type, BOM, initial bytes of the file |
| Parser hits version limits/differences | Behavior varies between environments | Jakarta Mail implementation, strictness properties |

Not every cause in the table will **always** produce `MailParseException`. For example, a wrong charset may only corrupt diacritics while parsing still succeeds; an attachment with invalid Base64 may only fail when reading the data stream. You must rely on the stack trace and the actual stage where the error occurs.

### Example of Truncated Raw MIME

~~~mime
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="b-abc"

--b-abc
Content-Type: text/plain

Hello
--b-abc
Content-Type: application/pdf
Content-Transfer-Encoding: base64

JVBERi0xLjQK...
~~~

This message is missing the closing marker `--b-abc--`. Depending on the parser, it may be rejected, still parsed with missing content, or report an error when traversing/serializing. Therefore, **do not rely solely on the absence of an exception** to conclude that raw MIME data is completely valid.

## 6. Reproducing Errors at the MIME Data Parsing Boundary

Suppose the application receives a `.eml` file from another system and needs to load it before sending or analyzing:

~~~java
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;
import org.springframework.mail.MailParseException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class RawMailImportService {
    private final JavaMailSender sender;

    public RawMailImportService(JavaMailSender sender) {
        this.sender = sender;
    }

    public MimeMessage readRawMessage(Resource resource)
            throws IOException {
        try (InputStream input = resource.getInputStream()) {
            return sender.createMimeMessage(input);
        } catch (MailParseException ex) {
            // Raw email data was rejected by the parser.
            // Log error type and record ID at the caller layer;
            // do not log the full mail body.
            throw ex;
        }
    }
}
~~~

`JavaMailSender.createMimeMessage(InputStream)` accepts a stream containing raw MIME and can represent parse errors using Spring `MailParseException`. In the code above, the `Resource` source can be a local file, an object storage adapter, or another storage source controlled by the application.

**Stream lifecycle note:** The method above closes the input stream after creating `MimeMessage`. Depending on the implementation and how parts are read, content may be buffered or lazily parsed. When integrating with a special stream source, ensure the message can continue reading its content in a way supported by the library; do not assume every `InputStream` has the same lifecycle.

### Checking the Error Context

When an exception occurs, determine:

- The file ID or outbox event currently being processed.
- Where the MIME data came from and which pipeline version generated it.
- Expected byte count vs. actual bytes read.
- Whether the failure happened during header parsing, part traversal, or body decoding.
- Root exception type and nested cause.
- Whether there were file read retries or partial downloads.

Do not print the entire MIME message in production logs because it may contain email addresses, tokens, private content, and attachments.
## 7. Errors Creating a New Message Are Not Necessarily MailParseException

A typical application does not load raw MIME, but instead creates an email from business data:

~~~java
MimeMessage mimeMessage = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mimeMessage, true, "UTF-8");
helper.setTo(customerEmail);
helper.setSubject("Order notification");
helper.setText(html, true);
~~~

Here there is no "parse from `.eml`" step; `MimeMessage` starts in an empty state. Common errors usually relate to:

- `customerEmail` is invalid.
- Content from a template or model is missing required fields.
- `MimeMessageHelper` was created with the wrong multipart mode.
- Inline image/attachment could not be read.
- Header value contains inappropriate characters.
- Message preparation threw an exception from another service.

These are **preparation/composition** errors and are not necessarily classified by Spring as `MailParseException`.

Example using `MimeMessagePreparator`:

~~~java
import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.mail.javamail.MimeMessagePreparator;

public void sendNotification(
        JavaMailSender sender,
        String recipient,
        String html) {

    MimeMessagePreparator preparator = message -> {
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");
        helper.setFrom("notifications@example.test");
        helper.setTo(recipient);
        helper.setSubject("System notification");
        helper.setText(html, true);
    };

    sender.send(preparator);
}
~~~

If `preparator.prepare(...)` throws an exception, Spring's mail sender may wrap this error into `MailPreparationException`. If preparation succeeds but SMTP transport fails, the exception may be `MailSendException` or `MailAuthenticationException`.

**The same invalid input value can lead to different exception types depending on the API and stage used by the application.** Do not write a single `catch (MailParseException)` and assume it covers all invalid messages.

### Error Unable to Read Resource Before SMTP

For example:

~~~java
helper.setText(html, true);
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/missing-logo.png"),
        "image/png");
~~~

If the resource does not exist, the error may occur while building or serializing MIME, depending on the overload and how Jakarta Mail reads the resource. This is a content preparation/data reading error, not SMTP authentication. Do not handle it by changing the SMTP port or increasing network retry timeouts.

## 8. Normalizing and Validating Data Before Creating MIME

The most effective prevention is to **filter invalid data out of the pipeline before calling mail APIs**. Do not delegate the entire validation responsibility to `MimeMessageHelper`.

### Validating Email Addresses

You can use `InternetAddress` to validate syntax at the Internet mail address level:

~~~java
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;

public final class MailAddressValidator {
    private MailAddressValidator() {
    }

    public static InternetAddress requireAddress(
            String raw) throws AddressException {
        if (raw == null || raw.isBlank()) {
            throw new AddressException("Email address is required");
        }

        InternetAddress address = new InternetAddress(raw, true);
        address.validate();
        return address;
    }
}
~~~

Usage:

~~~java
InternetAddress recipient =
        MailAddressValidator.requireAddress(request.recipient());

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, false, "UTF-8");

helper.setFrom("noreply@example.test");
helper.setTo(recipient);
helper.setSubject(request.subject());
helper.setText(request.body(), false);
~~~

Address syntax checking **does not prove the mailbox exists**, does not guarantee the domain has an MX record, and does not guarantee the SMTP provider will accept that recipient. If the system has a policy allowing only certain domains or verified recipients, additional checks must be performed at the application layer.

### Distinguishing Mailbox Address and Display Name

`"Nguyễn Văn A <a@example.test>"` consists of two parts: display name and mailbox address. For senders with Vietnamese names, pass the display name and charset through the appropriate API:

~~~java
import jakarta.mail.internet.InternetAddress;

InternetAddress sender = new InternetAddress(
        "noreply@example.test",
        "Bộ phận chăm sóc khách hàng",
        "UTF-8");

helper.setFrom(sender);
~~~

Do not manually concatenate the `From:` header from request strings and assign it raw into MIME. Use Jakarta Mail's structured API so the library encodes the required headers.

### Validating Subject

A subject is not binary data and should not be built by inserting raw CR/LF. A model can apply the following rules:

- Subject is required to be non-null and non-blank for specific email types.
- Limit length reasonably according to the product.
- Reject CR (`\r`), LF (`\n`), or unexpected control characters.
- Use a Unicode `String` and let Jakarta Mail handle header encoding.
- Do not manually Base64-encode the subject and pass an encoded-word as a normal subject.

Example:

~~~java
public static String requireSubject(String value) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException("Subject is required");
    }
    if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
        throw new IllegalArgumentException(
                "Subject must not contain CR/LF");
    }
    if (value.length() > 300) {
        throw new IllegalArgumentException("Subject is too long");
    }
    return value;
}
~~~

The threshold 300 in the example is an **illustrative application rule**, not a fixed maximum SMTP length. Actual headers have folding and encoded-word mechanisms; the library is responsible for converting the Unicode string into appropriate headers.

### Do Not Confuse HTML Escaping with MIME Parsing

If an HTML body contains a customer name with `<b>` or `&`, you need to escape the data when rendering the template; this is an HTML injection issue, not `MailParseException`. Use `th:text` in Thymeleaf for plain text or an equivalent HTML escaping mechanism.

Conversely, body content that is properly escaped can still render improperly if the multipart structure is wrong. **Data validation, HTML escaping, and MIME structure are three distinct responsibilities.**

## 9. Building MimeMessage Properly with MimeMessageHelper

A service that sends only HTML can use:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class CustomerMailComposer {
    private final JavaMailSender sender;

    public CustomerMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public MimeMessage compose(
            String recipient,
            String subject,
            String html) throws MessagingException {

        InternetAddress recipientAddress =
                MailAddressValidator.requireAddress(recipient);
        String validatedSubject = requireSubject(subject);

        if (html == null || html.isBlank()) {
            throw new IllegalArgumentException("HTML body is required");
        }

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                StandardCharsets.UTF_8.name());

        helper.setFrom("noreply@example.test");
        helper.setTo(recipientAddress);
        helper.setSubject(validatedSubject);
        helper.setText(html, true);

        return message;
    }
}
~~~

The example assumes `jakarta.mail.internet.InternetAddress` is imported and the `requireSubject` method is implemented as in the previous section. In a real project, place validators in a clear component instead of copying functions across multiple services.

### Why Does `multipart=false` Still Work for HTML?

An email with only `text/html` does not need multipart to be sent. The `true` parameter in `setText(html, true)` means **this body is HTML**; it is not the same as the `multipart` parameter in the helper's constructor.

Compare:

~~~java
// A single HTML body; no attachments or inline images.
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
helper.setText(html, true);
~~~

~~~java
// Has inline image or attachment: must use multipart.
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
helper.setText(html, true);
helper.addInline("logo", logoResource, "image/png");
~~~

Confusing these two booleans can cause code to call `addInline` on a helper not configured for multipart, leading to a preparation error.

### When Providing Plain and HTML Alternatives

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
helper.setText(
        "Order ORD-001 has been confirmed.",
        "<html lang=\"en\"><body>"
            + "<p>Order <strong>ORD-001</strong>"
            + " has been confirmed.</p>"
            + "</body></html>");
~~~

`setText(plainText, htmlText)` creates two versions of the content, allowing clients to choose a supported format. Do not pass HTML by mistake into the plain text argument, as clients may then display raw HTML tags or misread the alternative part.

## 10. Incorrect Multipart Structure Can Cause Late Errors

When an email has inline images and attachments, the MIME structure usually includes these relationships:

~~~text
multipart/mixed
  |
  +-- multipart/related
  |     |
  |     +-- multipart/alternative
  |     |     |
  |     |     +-- text/plain
  |     |     +-- text/html
  |     |
  |     +-- image/png
  |           Content-ID: <brand-logo>
  |
  +-- application/pdf
        Content-Disposition: attachment
~~~

This is a conceptual tree; the exact structure depends on the multipart mode and how the helper builds the message.

Errors that can occur:

- Declaring a boundary in the header without corresponding delimiters in the raw body.
- Adding an image as an attachment instead of an inline part.
- HTML references `cid:brand-logo` while the image part has a different `Content-ID`.
- Placing an attachment inside the related group even though it is not an HTML resource.
- Manually building a multipart hierarchy and forgetting to close or attach a child part.
- Using a `Content-Type` that does not match the actual data.

**Distinguishing syntax errors from rendering errors:** A mismatched CID may cause an image to disappear without causing `MailParseException` at all, because both parts are still valid MIME. An attachment with the wrong filename or an unsupported SVG in a client may only cause undesired UI rendering. Not every missing image is a parse error.

### Order When Adding Inline Resources

Spring recommends calling `addInline` **after** `setText`:

~~~java
helper.setText(html, true);
helper.addInline("brand-logo", logoResource, "image/png");
helper.addAttachment("invoice.pdf", pdfResource, "application/pdf");
~~~

Reversing the order may cause some mail clients to have trouble locating related resources. However, this issue is usually observed at rendering time and does not necessarily throw `MailParseException` during sending.

## 11. Charset, Header Encoding, and Transfer Encoding Are Different Layers

When Vietnamese emails have corrupted diacritics, determine which layer has the issue:

| Layer | Role | Example |
|---|---|---|
| Java Unicode String | Holds application data | `"Xin chào"` |
| Charset of MIME text part | Describes how characters are encoded into bytes | `charset=UTF-8` |
| `Content-Transfer-Encoding` | Encodes bytes for MIME transmission | `base64` or `quoted-printable` |
| MIME header encoding | Represents non-ASCII characters in headers | RFC 2047 encoded-word |
| Email client renderer | Decodes and renders content | Fonts, HTML/CSS, and support capabilities |

Body example:

~~~mime
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Xin ch=C3=A0o!</p>
~~~

The body is quoted-printable encoded; the client must decode it to UTF-8 and then display the Vietnamese characters. If the encoding metadata does not match the actual bytes, the content may have corrupted diacritics even though the parser throws no exception.

A subject can appear in raw MIME as:

~~~mime
Subject: =?UTF-8?B?Q2Fmw6k=?=
~~~

The client decodes this to `Café`. Do not read the raw header and assume that `=?UTF-8?...?=` characters in the source are a parse error; this is a valid header encoding format.

### Do Not Use `String.getBytes()` Without Specifying a Charset

When creating or saving raw MIME text using Java APIs, specify the appropriate charset:

~~~java
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
~~~

However, you **cannot** assume an entire MIME message can be created properly just by concatenating UTF-8 strings. Binary parts have their own transfer encodings, header folding, and MIME boundaries. For new emails, let Jakarta Mail build MIME from parts; for emails received externally, use a MIME parser rather than manually parsing with `String.split(...)` on boundaries.

## 12. Reading and Diagnosing the Exception Chain

For `MailParseException`, the most important question is: **where is the root cause?**

The chain might look like:

~~~text
MailParseException (Spring Mail)
    |
    +-- MessagingException (Jakarta Mail)
            |
            +-- ParseException / IOException / nested cause
~~~

This is a conceptual diagram. Not every error has exactly three layers or these exact exception types.

A simple function to extract the cause chain:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class ExceptionChain {
    private ExceptionChain() {
    }

    public static List<String> typeNames(Throwable failure) {
        List<String> names = new ArrayList<>();
        Throwable current = failure;
        int depth = 0;

        while (current != null && depth++ < 16) {
            names.add(current.getClass().getName());
            Throwable next = current.getCause();
            if (next == current) {
                break;
            }
            current = next;
        }
        return names;
    }
}
~~~

This function only records **exception class names**, without printing mail content or recipient data. When exception messages are needed, ensure they do not contain sensitive information and only log at the necessary level of detail.

In Jakarta Mail, `MessagingException` also has the concept of a *next exception* in addition to the standard cause chain:

~~~java
import jakarta.mail.MessagingException;

if (failure instanceof MessagingException messaging) {
    Exception next = messaging.getNextException();
    if (next != null) {
        // Record the type of next; do not print mail payload.
        String type = next.getClass().getName();
    }
}
~~~

Therefore, investigating SMTP/MIME errors should inspect both `cause` and nested exceptions provided by Jakarta Mail if present, rather than only reading the message of the outermost exception.

## 13. Diagnostic Workflow for MailParseException in a Spring Application

When errors appear in production, follow an order that narrows down the cause rather than changing SMTP configuration right away.

~~~mermaid
flowchart TD
    A[Mail processing failed] --> B{Reading raw MIME InputStream?}
    B -- Yes --> C[Check file/stream source and size]
    C --> D[Check exception chain + safe raw headers]
    D --> E{Did parser actually reject MIME?}
    E -- Yes --> F[Quarantine record and identify structural error]
    E -- No --> G[Check during part traversal or decoding]
    B -- No --> H[Creating a new MimeMessage]
    H --> I{Error before calling send?}
    I -- Yes --> J[Validate recipient/subject/template/resource]
    I -- No --> K[Check SMTP code/network/provider]
    G --> L[Classify data source and handling mechanism]
    F --> L
    J --> L
    K --> L
~~~

### Step 1 — Identify Which API Is Being Called

Look at the stack trace location:

- `createMimeMessage(InputStream)`: focus on the stream and raw MIME.
- `new MimeMessageHelper(...)` or `helper.setTo/setText/addInline`: focus on message preparation.
- `sender.send(MimeMessagePreparator)`: inspect the root error inside the preparator.
- `sender.send(MimeMessage)`: if preparation succeeded, inspect serialization/SMTP transport.
- `part.getContent()` or `message.getContent()`: errors may only appear when reading a part due to lazy parsing/decoding.

### Step 2 — Confirm the Source Data Is Complete

When raw MIME comes from a file or object storage:

- Verify the file exists and the application has read permissions.
- Compare the source file size with the actual number of bytes received.
- Confirm the upload/download process completed before parsing.
- If a checksum exists, verify the checksum against the stored data.
- Check that the source is not an HTML/PDF file renamed to `.eml`.
- Avoid operating on a stream that was partially read or closed before the library uses it.

When data arrives from a queue/broker, check whether the payload is subject to size limits or converted between bytes and `String`. Some systems drop bytes or alter newlines when encoding/decoding messages, making MIME no longer match the original.

### Step 3 — Analyze Headers Using Controlled Data

Some useful indicators:

- `Content-Type` has value `multipart/...` without a boundary.
- The boundary in the body differs from the declared boundary.
- A header has unclosed quotes or abnormal parameters.
- No blank line between header and body in a manually constructed section.
- Message is missing trailing bytes when there is a large attachment.
- `Content-Transfer-Encoding` is declared inconsistently with the actual data.

Perform analysis on **a sanitized copy of MIME in a test environment**; do not paste user emails into public tools. If reproduction is needed, keep the header/boundary structure but replace all recipients, sensitive subjects, and real bodies with dummy data.

### Step 4 — Determine Whether the Error Is Deterministic

If the same MIME blob always fails at the same step, it is very likely a data/structural error. Retrying without changing the content usually will not help.

If the error only occurs intermittently when reading a file over the network and disappears after re-downloading, it may be a transient I/O error. Check the checksum and upload completion status instead of prematurely treating the blob as permanently corrupted.

### Step 5 — Classify the Final State

A system with jobs/outbox should distinguish:

| Result | Meaning | Handling direction |
|---|---|---|
| `INVALID_INPUT` | Invalid business data | Reject before composing |
| `MIME_PARSE_FAILED` | Raw MIME cannot be parsed | Quarantine/DEAD and investigate source |
| `MIME_PREPARATION_FAILED` | Could not build message | Fix template, resource, recipient |
| `SMTP_RETRYABLE` | Transport/provider encountered transient error | Retry with backoff |
| `SMTP_PERMANENT` | SMTP rejected for non-recoverable reason | DEAD or manual handling |
| `SMTP_UNKNOWN` | Unclear whether SMTP accepted or not | Reconcile or retry per policy |
| `SUBMITTED` | SMTP server accepted message | Track delivery separately if needed |

These status names are application-level suggestions, not default Spring Mail enums.

## 14. Retry Rule: Parse Errors Usually Do Not Need SMTP Retries

A `MailParseException` caused by the same invalid raw MIME blob is usually **deterministic**. If you retry parsing those exact same bytes with the same parser without changing anything, the error will likely persist.

Example workflow:

~~~text
Read raw MIME blob
      |
      +-- Read failed due to object storage timeout
      |        |
      |        v
      |    Retry data retrieval
      |
      +-- Read complete, checksum valid
      |        |
      |        v
      |    Parse fails consistently
      |        |
      |        v
      |    Quarantine / fix source data
      |
      +-- Parse succeeded
               |
               v
           Compose / send
~~~

**Do not retry SMTP when there is no valid MimeMessage to send.** If the message was not built successfully, the SMTP server never received the corresponding submission request from that job.

### Important Exception: Data Source Changes Between Reads

A file may be mid-upload, or object storage may return inconsistent data due to a pipeline bug. In this case, retrying the *data retrieval* step after confirming the upload completed may be reasonable. Do not call that "retrying MailParseException" without understanding why the data differs on subsequent reads.

### SMTP Failure After Message Transmission Begins

If the message was created and sent to SMTP but the connection drops mid-way, the outcome may be unknown. When SMTP has already received the body and returned success but the application has not saved state, retrying may send duplicates. Therefore, transport errors need their own policy, completely different from parse errors on a fixed MIME blob.

## 15. Structured Logging and Data Protection

Useful logs should help identify **which step** failed without copying the entire email.

Example application-level log record:

~~~text
event=mail_processing_failed
mailJobId=job-7f3e
phase=parse_raw_mime
exceptionType=org.springframework.mail.MailParseException
sourceType=object_storage
rawMimeBytes=187436
attempt=1
correlationId=req-84f0
classification=MIME_PARSE_FAILED
~~~

Consider logging only fields needed for operations. In particular:

- Do not log full `From`, `To`, `Cc`, `Bcc` unless necessary.
- Do not log reset tokens, OTPs, HTML bodies, attachments, or raw MIME.
- Do not print stack traces containing sensitive data to public log systems.
- Do not use subjects as metric labels due to sensitive data and high cardinality.
- Limit retention periods for logs/quarantined blobs and restrict access permissions.

### Separating Error Codes from Exception Messages

Exception messages from libraries can change across versions and may contain portions of input data. Instead of having application logic rely on `message.contains("boundary")`, standardize error codes:

~~~java
public enum MailProcessingFailureCode {
    INVALID_RECIPIENT,
    INVALID_SUBJECT,
    MIME_PARSE_FAILED,
    MIME_PREPARATION_FAILED,
    RESOURCE_READ_FAILED,
    SMTP_AUTH_FAILED,
    SMTP_SUBMISSION_FAILED,
    SMTP_SUBMISSION_UNKNOWN
}
~~~

Do not infer a more specific error code than actual evidence supports. If the parser only returns a generic exception and does not specify exactly which header is wrong, record `MIME_PARSE_FAILED` rather than claiming a specific boundary is faulty.

### Restricting Storage of Raw MIME for Investigation

A raw MIME message may contain:

- Real email addresses and names.
- Order data, payment details, personal information.
- Links with access tokens.
- Attachments containing internal documents.
- Header information reflecting transport infrastructure.

If you need to keep failing files for reproduction, store them in an encrypted store with restricted permissions, defined deletion retention, and reference IDs in logs. Dummy or sanitized data should be the default choice for documentation, issue trackers, and test samples.

## 16. Do Not Manually Patch Raw MIME Using Arbitrary String Manipulation

Some snippets try to "fix" emails like this:

~~~java
String raw = new String(rawBytes, StandardCharsets.UTF_8);
raw = raw.replace("\\n", "\\r\\n");
raw = raw.replace("boundary=bad", "boundary=good");
byte[] fixedBytes = raw.getBytes(StandardCharsets.UTF_8);
~~~

This approach is **unsafe for data integrity**:

- MIME can contain binary parts or data encoded in multiple charsets.
- The entire raw MIME is not necessarily a plain Unicode text document.
- Newline normalization does not distinguish boundary lines, header folding, and body text.
- Replacing the boundary string in the header without changing the actual delimiters can make the error worse.
- Converting bytes to `String` and back can corrupt non-UTF-8 data.

If you need to fix raw MIME generated by your own system, fix **the message builder from the canonical data source** and re-serialize using Jakarta Mail. If processing emails received from external systems, preserve the original and design a controlled parser/quarantine; do not blindly "repair" it just to bypass an exception.

### Which Parts Should Be Built via API Instead of String Concatenation?

| Component | Recommended approach |
|---|---|
| From/To/Reply-To | `InternetAddress` and helper methods |
| Unicode Subject | `setSubject` accepting a Java `String` |
| Plain text body | `setText(text, false)` |
| HTML body | `setText(html, true)` |
| Plain + HTML | `setText(plain, html)` |
| Inline image | `addInline(contentId, resource, mediaType)` |
| Attachment | `addAttachment(filename, resource, mediaType)` |
| Multipart structure | Let `MimeMessageHelper` manage it whenever possible |

Manual raw header/body concatenation should only be used when there is a special need and a thorough understanding of Internet Message Format, MIME boundaries, charsets, and transfer encodings.

## 17. Separating MIME Errors from HTML Template Errors

An email template can fail before MIME is created:

~~~text
Template context missing required value
        |
        v
Thymeleaf render exception
        |
        v
Failed to generate HTML
        |
        v
No SMTP submission yet
~~~

Another template renders valid HTML but contains wrong content:

~~~html
<p>Order ID: null</p>
~~~

This is a **data semantic error** and may still be sent over SMTP successfully. No `MailParseException` is guaranteed to occur.

Therefore, two layers of control are needed:

1. **Pre-rendering validation** for required fields, recipient, subject, URLs, and business data.
2. **MIME composition checks** for charset, part structure, `Content-ID`, and attachments.

If an email is generated by a template engine and then passed to `MimeMessageHelper`, template errors should usually be classified as `MIME_PREPARATION_FAILED` or `TEMPLATE_RENDER_FAILED` per application convention, rather than labeled `MailParseException`.

## 18. Testing MIME Round-Trip Without an SMTP Server

A useful test is to build a message from valid data, serialize it into raw bytes, parse it back, and verify the decoded content. This test does not send real emails, but proves the application produces a MIME message that Jakarta Mail can read back.

Example with **JUnit Jupiter** and **AssertJ**:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;

class MailMimeRoundTripTest {
    @Test
    void roundTripsVietnameseSubjectAndHtmlBody() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage original = new MimeMessage(session);

        MimeMessageHelper helper = new MimeMessageHelper(
                original,
                false,
                StandardCharsets.UTF_8.name());
        helper.setFrom("noreply@example.test");
        helper.setTo("customer@example.test");
        helper.setSubject("Đơn hàng đã xác nhận ✅");
        helper.setText(
                "<html lang=\"vi\"><body>"
                    + "<p>Xin chào, đơn hàng của bạn đã được xác nhận.</p>"
                    + "</body></html>",
                true);

        original.saveChanges();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        original.writeTo(output);

        JavaMailSenderImpl parser = new JavaMailSenderImpl();
        MimeMessage parsed = parser.createMimeMessage(
                new ByteArrayInputStream(output.toByteArray()));

        assertThat(parsed.getSubject())
                .isEqualTo("Đơn hàng đã xác nhận ✅");
        assertThat(parsed.isMimeType("text/html")).isTrue();
        assertThat((String) parsed.getContent())
                .contains("Xin chào, đơn hàng của bạn");
    }
}
~~~

In the test:

- `saveChanges()` updates necessary MIME metadata before serialization.
- `writeTo(...)` converts the message into bytes, including header/transfer encoding.
- `createMimeMessage(InputStream)` parses back from bytes, exercising the MIME reading path.
- `getSubject()` and `getContent()` are used to inspect decoded data.
- There is no SMTP host, username, or password; the test does not call `send(...)`.

This test intentionally uses a simple `text/html` part. If the message has `multipart/alternative`, inline images, or attachments, `getContent()` may return `Multipart` instead of `String`; in that case, traverse the part tree.

### Traversing Parts by Content Type

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import jakarta.mail.MessagingException;

static String findHtmlBody(Part part)
        throws MessagingException, IOException {
    if (part.isMimeType("text/html")) {
        Object content = part.getContent();
        return content instanceof String text ? text : null;
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();
        for (int i = 0; i < multipart.getCount(); i++) {
            String html = findHtmlBody(multipart.getBodyPart(i));
            if (html != null) {
                return html;
            }
        }
    }
    return null;
}
~~~

This snippet finds the HTML body in a basic multipart tree. For very complex emails, there may be nested `message/rfc822` or multiple HTML alternatives; the application needs a policy to choose the semantically right part. Do not assume part index 0 is always HTML.

## 19. Testing Invalid Input Without Depending on Parser Strictness

An important test is verifying **invalid data is blocked before building the message**:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.mail.internet.AddressException;
import org.junit.jupiter.api.Test;

class MailAddressValidatorTest {
    @Test
    void rejectsMalformedRecipient() {
        assertThatThrownBy(() ->
                MailAddressValidator.requireAddress("not-an-email"))
                .isInstanceOf(AddressException.class);
    }

    @Test
    void rejectsMissingRecipient() {
        assertThatThrownBy(() ->
                MailAddressValidator.requireAddress("   "))
                .isInstanceOf(AddressException.class);
    }
}
~~~

Another test for subject:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class MailSubjectValidatorTest {
    @Test
    void rejectsHeaderLineBreak() {
        String suspicious =
                "Receipt\r\nBcc: hidden@example.test";

        assertThatThrownBy(() -> requireSubject(suspicious))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

`requireSubject` is the illustrative validation method from the previous section. This test detects header data with unexpected CR/LF and rejects it before using Jakarta Mail.

### Why Should You Not Assert "Any Invalid MIME Must Throw MailParseException"?

Real-world mail parsers often have **tolerant parsing** modes to read imperfect emails in the wild. For example:

- A missing closing boundary may be partially accepted by the parser.
- A missing header may result in a null value rather than an exception.
- A wrong `Content-Type` may cause content to be interpreted as another part.
- A Base64 error may only appear when reading the body stream.

Therefore, a test that constructs a "wrong-looking" raw string and asserts `MailParseException` may be unstable across Jakarta Mail versions. Tests should:

1. Know precisely which errors the implementation in use reports.
2. Check the state/semantics of the parsed message, not just "constructor did not throw an exception".
3. Separate **application-managed validation** tests from **parser fault-tolerance** tests.
4. If testing catch branches is needed, simulate exceptions at the abstraction boundary using mocks/stubs rather than relying on an arbitrary non-standard raw sample that the parser is not guaranteed to reject.

### Testing I/O Errors When Reading Data

If input is downloaded from object storage, use a fake resource that throws `IOException` to test that the system classifies it as a retryable **resource read failure**, not conflated with malformed MIME:

~~~java
InputStreamSource brokenSource = () -> {
    throw new IOException("Temporary object storage failure");
};
~~~

This test illustrates a stream retrieval error; it is not an example guaranteeing `MailParseException`. Separating the two cases keeps retry logic from putting a corrupted MIME blob into an infinite network retry loop.

## 20. Handling MailParseException in the Mail Sending Workflow

If an application imports raw MIME and resends it, it can organize a service to handle outcomes:

~~~java
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.Resource;
import org.springframework.mail.MailParseException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ImportedMailDispatcher {
    private final JavaMailSender sender;
    private final MailJobStateStore jobStore;

    public ImportedMailDispatcher(
            JavaMailSender sender,
            MailJobStateStore jobStore) {
        this.sender = sender;
        this.jobStore = jobStore;
    }

    public void dispatch(String jobId, Resource rawMime) {
        MimeMessage message;

        try (InputStream stream = rawMime.getInputStream()) {
            message = sender.createMimeMessage(stream);
        } catch (MailParseException ex) {
            jobStore.markDead(jobId, "MIME_PARSE_FAILED");
            return;
        } catch (IOException ex) {
            jobStore.scheduleRetry(jobId, "RESOURCE_READ_FAILED");
            return;
        }

        try {
            sender.send(message);
            jobStore.markSubmitted(jobId);
        } catch (MailSendException ex) {
            jobStore.recordSubmissionFailure(jobId, ex);
        }
    }
}
~~~

`MailJobStateStore` is an application-defined interface, not a built-in Spring API. The example's purpose is to show **classification boundaries**:

- Raw MIME parse errors are handled before calling `send`.
- Transient source read errors are separated from corrupted data errors.
- SMTP errors occur at the submission stage and have their own policy.

This is an illustrative skeleton and does not yet cover all `MailException` subtypes, leases/idempotency, security/quarantine, and lazy parsing that may raise errors later. In a real system, the worker needs to catch appropriate exceptions at each stage, persist state in separate transactions, and must not mark `SUBMITTED` if submission is not confirmed.

### Stream Lifecycle Issues When Resending Imported MIME

Depending on the source and implementation, the parser may read/buffer part or all of the message when the constructor runs. If `send(...)` later needs to re-read a part from an already-closed source, an error can occur. For import/resend workflows, choose a stable way to retain data:

- Save the MIME blob into a secure temporary file or object storage and create a re-readable source.
- Limit size and checksum data before parsing.
- Confirm `MimeMessage` can still be re-serialized after the source `InputStream` is released.
- For one-shot sources, you may need to create an intermediate byte/file copy or deserialize using an appropriate API.

Do not turn an I/O exception when serializing an attachment later into a conclusion that "the MIME parser did not understand the header" if actual evidence shows the resource is no longer readable.

## 21. When Importing MIME, Limit Size and Resources

A `.eml` input from an external system may contain very large attachments or many nested parts. Even if the parser handles the syntax, reading the entire message into memory can cause heap pressure.

A safe input ingestion policy should include:

- Limiting raw MIME size before parsing.
- Limiting the number of attachments and size of each attachment when reading content.
- Limiting depth of multipart or nested messages if needed.
- Timeouts and byte limits when downloading from object storage or URLs.
- Accepting only authenticated/authorized data sources.
- Not rendering external HTML in a privileged context.
- Checking actual file type, not relying solely on the `.eml` filename.
- Having a quarantine policy when untrusted payloads are detected.

Example with a local file managed by the application:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public MimeMessage readBoundedMail(Path path) throws Exception {
    long maxBytes = 10L * 1024 * 1024;

    if (Files.size(path) > maxBytes) {
        throw new IllegalArgumentException("Raw MIME is too large");
    }

    try (InputStream stream = Files.newInputStream(path)) {
        return sender.createMimeMessage(stream);
    }
}
~~~

This is only a pre-read file size check, suitable when the file resides in managed storage. If the file can be replaced/appended concurrently between `Files.size(...)` and `newInputStream(...)`, a snapshot mechanism or byte limit during reading is required. For network streams without reliable sizes, a true bounded reader is necessary. Do not trust `Content-Length` from unauthenticated input as an absolute size guarantee.

The 10 MiB value is only illustrative. Actual thresholds depend on email types, provider limits, memory budgets, attachment sizes, and product policies.

## 22. Distinguishing Parse Errors from Connection and Authentication Errors

An application log may generically record "Cannot send email" for many causes. However, handling depends on the stage:

~~~text
Input / template / raw MIME
         |
         +-- Validation failed
         |
         +-- MIME parse failed
         |
         +-- MIME preparation failed
         |
         v
Valid MimeMessage
         |
         v
SMTP connection + authentication
         |
         +-- Connection refused/timeout
         |
         +-- Authentication rejected
         |
         v
MAIL FROM / RCPT TO / DATA
         |
         +-- SMTP 4xx / 5xx
         |
         v
SMTP accepted
         |
         v
Delivery / mailbox processing
~~~

For example, fixing the SMTP host/port or password **cannot resolve** a `MailParseException` caused by raw MIME with an unparseable header. Conversely, fixing a template's `Content-Type` will not solve `535 Authentication credentials invalid`.

| Observed information | Primary likelihood | Handling step |
|---|---|---|
| Stack trace at `createMimeMessage(InputStream)` | Raw MIME parsing | Check input bytes, stream, headers |
| Exception in `MimeMessagePreparator` | Composition/preparation | Check model, recipient, template, resource |
| `AddressException` before sending | Invalid address | Email address validation |
| `MailAuthenticationException` error | SMTP authentication | Secrets/config/account policy |
| Connect timeout on submission | Network/provider | Timeouts, DNS, firewall, SMTP availability |
| Provider returns SMTP 4xx | Transient error or rate limit | Retry with backoff per policy |
| Provider returns SMTP 5xx | Usually permanent error depending on code | Check recipient/sender/domain/policy |
| SMTP accepted but client does not render image | Rendering/MIME relationship | Check CID, multipart, email client |

Classify the stage first, then inspect the exact nested exception. An error can arise when Jakarta Mail serializes the message during `send(...)` rather than necessarily on the network, so do not conclude solely from the top-level method name.

## 23. Proper SMTP Config Cannot Fix a Corrupted MIME Blob

In Spring Boot, sender configuration may look like:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: \${SMTP_USERNAME}
    password: \${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 10000
      mail.smtp.writetimeout: 10000
~~~

These properties control connections and SMTP behavior. They **do not make the parser automatically fix malformed MIME headers**, do not add missing multipart boundaries, and do not turn a renamed PDF file into a valid raw email.

Distinguish clearly:

- **MIME parsing:** how the library interprets raw message structure.
- **MIME composition:** how the application constructs headers, body, and parts.
- **SMTP transport:** how the message is submitted over the network.

Configuring a charset when using `MimeMessageHelper(..., "UTF-8")` helps construct text parts properly, but cannot fix a raw MIME whose bytes were already corrupted before import.

## 24. Anti-Patterns When Handling MailParseException

### 24.1. Catching Every MailException and Retrying Immediately

~~~java
try {
    processMail(job);
} catch (MailException ex) {
    retryImmediately(job);
}
~~~

If the cause is an invalid MIME blob, looping endlessly does not change the data. Aggressive retries increase load, fill up backlogs, and obscure source errors. You must separate parse, preparation, authentication, and submission.

### 24.2. Grouping Application Errors into "SMTP Unavailable"

If a template fails to render or a recipient has invalid syntax, the system should not display "SMTP server down". A wrong error code misleads operations into checking the wrong component, slowing down remediation and potentially increasing unnecessary retries.

### 24.3. Catching Only MailParseException Everywhere

~~~java
try {
    helper.setTo(recipient);
    helper.setText(html, true);
    sender.send(message);
} catch (MailParseException ex) {
    // Does not cover all preparation or SMTP errors.
}
~~~

The example above does not fully handle `MessagingException`, `MailPreparationException`, and other Spring Mail subtypes. Catch at clear boundaries and preserve causes for classification.

### 24.4. Ignoring Errors and Still Marking Email as Sent

~~~java
try {
    sender.send(message);
} catch (Exception ex) {
    logger.warn("Ignoring mail failure");
}
job.markSubmitted(); // Incorrect status semantics.
~~~

`SUBMITTED` should only be recorded when there is evidence of successful SMTP submission. If parse/preparation fails, no valid mail was sent. If the transport outcome is uncertain, use a corresponding status rather than assuming success.

### 24.5. Logging Full Raw MIME for Quick Debugging

Sending raw MIME to production logs can expose OTPs, tokens, attachments, and personal data. Log phase, correlation ID, size, exception type, and sanitized metadata. If failing blobs must be kept, store them in a controlled store with clear retention.

### 24.6. Splitting Emails Manually Using String.split

Do not manually split MIME using `split("--boundary")` or parse headers by finding the first `:` across the entire message. Headers can be folded, bodies can contain encoded data, and boundaries have specific rules. Use Jakarta Mail.

### 24.7. Assuming Successful Parsing Means the Message Is Business-Valid

A MIME message without `To`, with an empty Subject, or containing stale data may still be parsed. Being able to "read MIME" does not equate to "eligible to send". Separate validation is required for the use case and sending policy.

### 24.8. Suppressing Errors by Replacing All Unknown Characters with Question Marks

Incorrect charset conversion can destroy original data. If bytes are lost before encoding, no MIME property can recover the content. Fix it at the source and preserve Unicode/byte data when passing across systems.

### 24.9. Retrying Raw MIME on the Same Data Without Preserving the Original

If a pipeline "patches" a blob on every retry, data can mutate uncontrollably and become impossible to investigate. Keep the original raw copy with a checksum, record the parser/pipeline version, and generate modified copies as separate artifacts when truly needed.

## 25. Test Scenarios Suite for a Spring Mail Application

A concise yet useful test suite may include:

| ID | Scenario | Expected outcome |
|---|---|---|
| TC-01 | Build valid HTML + Vietnamese Subject | MIME serializes and parses back cleanly |
| TC-02 | Recipient missing `@` character | Validation rejects before sending |
| TC-03 | Recipient is null/blank | Validation rejects |
| TC-04 | Subject contains CR/LF | Validation rejects |
| TC-05 | Template missing required field | Preparation fails, SMTP not called |
| TC-06 | Image/attachment file does not exist | Resource/preparation error classified |
| TC-07 | Valid raw MIME from file | `createMimeMessage(InputStream)` creates message |
| TC-08 | Raw MIME corrupted per parser in use | Parse error reported/quarantined properly |
| TC-09 | `InputStream` source throws `IOException` | Classified as read error, not mislabeled malformed MIME |
| TC-10 | Multipart with HTML and inline CID | Image part exists and `Content-ID` matches |
| TC-11 | Wrong SMTP AUTH | Classified as authentication, not parse |
| TC-12 | SMTP timeout before submission | Retried according to transport policy |
| TC-13 | Outcome after DATA uncertain | Do not automatically record delivery/exactly-once |
| TC-14 | One job fails in batch | Other jobs continue processing independently |

Recommended testing layers:

- **Unit tests** for model/recipient/subject validation and error classification.
- **MIME round-trip tests** with `MimeMessage.writeTo(...)` and `createMimeMessage(InputStream)`.
- **Database tests** if jobs/outbox have state transitions and retries.
- **SMTP sink integration tests** when needing to verify raw MIME sent over the protocol.
- **Client rendering tests** when the issue lies in HTML/inline images.

Do not use production SMTP accounts or real recipients to reproduce parser bugs. MIME tests can run entirely in memory without credentials.

## 26. Operating Batch Mail When Corrupted Messages Exist

If a worker processes multiple outbox records in a batch, one corrupted raw MIME should not **lose the state of the entire batch**:

~~~text
Batch:
  Job A -> parse succeeded -> send
  Job B -> MailParseException -> quarantine
  Job C -> parse succeeded -> send

Worker continues processing jobs independently
and records results separately for each job.
~~~

Principles:

1. Each job has a stable ID/correlation ID.
2. Parse failure of one job is recorded as its own state, not swallowed to lose the record.
3. If data is permanently corrupted, do not retry endlessly.
4. If transient I/O error, retry with backoff and limit.
5. Do not treat SMTP acceptance as final delivery.
6. If SMTP outcome is uncertain, consider duplicates before retrying.
7. Do not delete important data before state and audit are committed.
8. If the worker crashes, unfinished jobs can be re-claimed via lease, not relying solely on an in-memory RAM queue.

### Metrics to Monitor

| Metric | Meaning |
|---|---|
| `mail_parse_failure_total` | Count of raw MIME parse errors |
| `mail_preparation_failure_total` | Count of email build/preparation errors |
| `mail_resource_read_failure_total` | Count of input/resource read errors |
| `mail_submission_failure_total` | Count of SMTP submission errors |
| `mail_job_dead_total` | Count of jobs requiring intervention |
| `mail_job_retry_count` | Count of jobs awaiting retry |
| `mail_job_oldest_pending_age` | Longest waiting time |
| `mail_processing_duration` | Processing duration by phase |

Metrics should have low-cardinality tags by **phase**, **error code**, and **email type**. Do not put raw `recipient`, `subject`, `jobId`, or exception messages as metric labels.

### Alerting

Some scenarios worth alerting on:

- Sudden spike in `MailParseException` right after deploying a MIME pipeline change.
- All jobs imported from the same source fail parsing.
- Resource read error rate rises at the same time object storage experiences an incident.
- Mass SMTP AUTH errors even though MIME round-trip tests still succeed.
- Backlog of `DEAD`/`UNKNOWN` jobs grows or goes unprocessed.

This information helps determine whether to roll back a MIME serializer change, investigate data ingestion, or fix SMTP provider configuration.

## 27. Frequently Asked Questions

**Does MailParseException mean the SMTP server is down?** No. It usually indicates a problem while parsing a mail message. SMTP connection and authentication are separate stages.

**Does missing Subject or To always cause the parser to throw MailParseException?** Not necessarily. A MIME parser may still read a message missing some headers. The application must validate business-required fields.

**Why does the same raw email parse in a mail client but fail in the application?** Parsers can differ in tolerant parsing levels, configuration, and how parts are read. Compare raw bytes, implementation/version, and failure stage; do not assume one side is definitely wrong.

**How do MailParseException and MailPreparationException differ?** Parse exceptions point to being unable to read/parse a mail message; preparation exceptions point to errors while executing message construction/preparation logic, such as in `MimeMessagePreparator`.

**Is an invalid recipient address error always MailParseException?** No. It usually involves `AddressException`/`MessagingException` or a corresponding preparation error; if the server rejects a syntactically valid recipient, that is an SMTP error.

**Does changing charset to UTF-8 automatically fix corrupted raw MIME?** No. UTF-8 only addresses text representation when bytes and metadata are consistent. Wrong boundaries, truncated sources, or broken streams are not fixed by changing charset.

**Can MIME be parsed by forcing the entire InputStream into a UTF-8 String?** No. A raw MIME message can contain multiple parts with different transfer encodings and charsets; forcing everything to UTF-8 can corrupt data.

**Will a .eml file missing its closing boundary definitely be rejected?** No. Jakarta Mail's tolerant parsing may allow partial parsing. Tests should check actual received semantics/parts, not rely on an arbitrary "invalid" sample.

**Should MailParseException be retried indefinitely?** No. For permanently corrupted raw bytes, quarantine and fix the source. Only retry reading/downloading if there is evidence of transient errors or incomplete source data.

**If the error occurs after calling send, is it a parse error or SMTP error?** Read the stack trace and nested causes. MIME serialization can happen during sending; do not conclude based solely on the method name.

**Does a successful SMTP send mean the MIME body is correct?** No. The server may accept a message that email clients fail to render as expected. Test MIME and rendering independently.

## 28. Recommended Handling Workflow

~~~text
1. Receive request or raw MIME.
2. Validate data source, size, and access permissions.
3. If building a new email: validate recipient, subject, model/template.
4. If importing raw MIME: parse with Jakarta Mail, do not split manually.
5. If MailParseException occurs:
      - safely log ID/phase/cause type
      - determine whether read source error or permanent structural error
      - retry fetch if transient, quarantine if blob is corrupted
6. If preparation fails: fix model/template/resource, do not blindly retry SMTP.
7. Serialize and inspect MIME when diagnostics are needed.
8. Send via JavaMailSender.
9. Classify SMTP acceptance, rejection, or UNKNOWN.
10. Record per-job state and monitor metrics.
~~~

**Final principle:** `MailParseException` is a signal to investigate the **message parsing boundary**, not a generic label for every email that fails to send. In Spring Framework Mail, distinguish parsing existing MIME data, building messages with `MimeMessageHelper`, and sending over SMTP; validate data before creation, read the exception chain carefully, run round-trip tests, protect raw MIME, and apply retries at the right phase. Classifying errors accurately enables faster resolution, prevents duplicate sends, and keeps one corrupted message from clogging the entire mail system.
