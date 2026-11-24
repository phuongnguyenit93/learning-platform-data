# When to Use the Helper vs. Creating Multipart Directly

In **Spring Framework Mail**, there are two main ways to create multi-part MIME email content: using Spring's `MimeMessageHelper` utility or manually assembling `MimeMultipart` and `MimeBodyPart` groups with Jakarta Mail. Both produce a `MimeMessage` sendable via `JavaMailSender`, yet the level of control and developer responsibility differ.

`MimeMessageHelper` fits common emails: a single text/HTML body, both plain text and HTML versions, inline images, attachments, or combinations thereof. When requirements demand exact control over the MIME tree, subtypes, ordering, parameters, per-part headers, or specialized packaging formats, you can construct multiparts directly with Jakarta Mail.

The key is choosing the API based on **the MIME structure the email genuinely needs**. Using low-level APIs for a simple email lengthens code and increases handling burden. Conversely, forcing a specialized structure into the helper can yield a MIME tree that fails to match the receiver's contract.

This lesson explains both approaches, how to choose by need, complete Java examples, how they integrate with the Spring sender, inspecting MIME source, and mistakes to avoid.

## 1. What Components Make Up a MIME Message?

A MIME email does not necessarily have just one body. It can contain multiple parts and nested multipart groups.

Simple text email:

```text
MimeMessage
└── text/plain; charset=UTF-8
```

Email with two alternative content formats:

```text
MimeMessage
└── multipart/alternative
    ├── text/plain; charset=UTF-8
    └── text/html; charset=UTF-8
```

HTML email with inline image and attachment:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── text/html
    │   └── image/png; Content-ID: <brand-logo>
    └── application/pdf; attachment
```

Multipart types express different relationships:

| Content-Type | Meaning | Example |
|---|---|---|
| `multipart/alternative` | Alternative versions of the same content; client selects suitable format. | Plain text and HTML. |
| `multipart/related` | Root content and resources needed to render that content. | HTML and CID images. |
| `multipart/mixed` | Independent coexisting parts. | Email body and PDF attachment. |
| `multipart/report` | Structured report per MIME conventions. | Delivery Status Notification. |
| `multipart/signed` | Content accompanied by a signature per MIME digital signature standard. | S/MIME signed message. |

Groups can be nested. For example, an email with plain text, HTML, inline images, and a PDF can use mixed on the outside, related to group HTML/images, and alternative to group content versions. The specific tree must reflect each part's actual meaning.

## 2. What Is MimeMessageHelper?

`MimeMessageHelper` is a Spring utility class in the package:

```java
org.springframework.mail.javamail.MimeMessageHelper
```

It wraps a `jakarta.mail.internet.MimeMessage` and provides a high-level API for configuring email fields and common MIME components.

Common operations:

| API | Purpose |
|---|---|
| `setFrom(...)` | Sender email address and display name. |
| `setTo(...)`, `setCc(...)`, `setBcc(...)` | Primary recipients and copy recipients. |
| `setReplyTo(...)` | Address to receive replies. |
| `setSubject(...)` | Email subject. |
| `setText(text)` | Plain text body. |
| `setText(html, true)` | Single HTML body. |
| `setText(plain, html)` | Both plain text and HTML versions. |
| `addInline(...)` | Add inline resources, typically images referenced by CID. |
| `addAttachment(...)` | Add file attachments. |

Simple HTML email example:

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setFrom("notice@example.org");
helper.setTo("user@example.net");
helper.setSubject("Notification");
helper.setText("<p>Hello!</p>", true);

mailSender.send(message);
```

The helper handles many routine MIME details such as charset, part creation, content type, and attachment metadata. As a result, the email-sending service can focus on business content.

### Helper Multipart Modes

When multiple parts are needed, constructors let you select a multipart mode:

```java
new MimeMessageHelper(message, multipart, encoding);
new MimeMessageHelper(message, multipartMode, encoding);
```

Primary modes:

| Constant | Structure configured by helper | Common use case |
|---|---|---|
| `MULTIPART_MODE_NO` | No multipart created | Single text or HTML body. |
| `MULTIPART_MODE_MIXED` | `multipart/mixed` | Body and attachments. |
| `MULTIPART_MODE_RELATED` | `multipart/related` | Body and inline resources. |
| `MULTIPART_MODE_MIXED_RELATED` | Outer `multipart/mixed`, inner `multipart/related` | Inline resources together with independent attachments. |

Example with only inline images:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);
```

Example with inline images and PDF:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
```

Mode names describe the multipart shape at the helper level. When a system demands a stricter MIME tree, serialize the message and confirm the actual structure rather than inferring solely from constant names.

## 3. When Should You Use MimeMessageHelper?

Choose the helper when the email falls within scenarios Spring supports directly.

### 3.1. Text-Only or HTML-Only Email

If there is only one body, the helper keeps code concise and clear:

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setFrom("support@example.org");
helper.setTo(recipient);
helper.setSubject("Request Received");
helper.setText(
        "<html><body><h1>We have received your request.</h1></body></html>",
        true
);

mailSender.send(message);
```

There is no need to create `MimeMultipart` manually since the message has only one content part.

### 3.2. Plain Text and HTML as Two Alternative Versions

If you want mail clients to pick one of two formats, use the two-string overload:

```java
helper.setText(
        "Order ORD-001 has been confirmed.",
        "<p>Order <strong>ORD-001</strong> has been confirmed.</p>"
);
```

The helper builds appropriate alternative content. The plain text version must still convey all important facts and actions if the recipient does not render HTML.

### 3.3. HTML with Inline Images

Use `addInline(...)` with a Content-ID matching the CID URL in HTML:

```java
String logoCid = "brand-logo";

helper.setText(
        "<html><body>"
                + "<h1>Hello!</h1>"
                + "<img src=\"cid:" + logoCid + "\" alt=\"Logo\">"
                + "</body></html>",
        true
);

helper.addInline(
        logoCid,
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
```

Call `setText(...)` before `addInline(...)`. Spring documentation highlights this ordering to improve the likelihood that mail clients recognize inline resources accurately.

### 3.4. Standard Attachments

`addAttachment(...)` suffices when simply adding files:

```java
helper.setText("The report is attached to this email.");

helper.addAttachment(
        "report.pdf",
        new ClassPathResource("mail/report.pdf"),
        "application/pdf"
);
```

If the email also has inline images, choose `MULTIPART_MODE_MIXED_RELATED` so the helper organizes related and mixed according to the structure supported by that mode.

### 3.5. Standard Headers and Charsets

The helper also fits when setting From, Reply-To, To/Cc/Bcc, subject, display names, and charsets. These operations do not require managing individual `MimeBodyPart` instances directly.

**Practical rule:** if the helper APIs express the email you want to send, use the helper. It reduces the number of MIME details you have to manage manually and keeps business code readable.

## 4. Complete Example with MimeMessageHelper

Suppose an order confirmation email needs:

- Plain text as fallback content.
- HTML for nicer presentation.
- Inline logo referenced via CID.
- Attached PDF for the recipient to download.

A service:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        String logoCid = "order-brand-logo";

        helper.setFrom("orders@example.org", "Example Store");
        helper.setTo(recipient);
        helper.setSubject("Order Confirmation ORD-001");

        String plainText = """
                Order ORD-001 has been confirmed.
                See the report in the attached report.pdf file.
                """;

        String htmlText = """
                <html>
                  <body>
                    <img src="cid:order-brand-logo"
                         alt="Example Store"
                         width="140">
                    <h1>Order Confirmed</h1>
                    <p>Order code: <strong>ORD-001</strong></p>
                    <p>Please see the attached report.</p>
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);

        helper.addInline(
                logoCid,
                new ClassPathResource("mail/brand-logo.png"),
                "image/png"
        );

        helper.addAttachment(
                "report.pdf",
                new ClassPathResource("mail/report.pdf"),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
```

The code illustrates common operations directly supported by the helper. Filenames on the classpath must exist in the running application artifact. In real systems, CIDs may be generated uniquely per message, and order codes and content are passed from business logic instead of being hardcoded.

### Why Does This Example Fit the Helper?

There are no special requirements for part ordering, custom subtypes, custom MIME parameters, or a mandatory custom nesting tree. The email only needs plain/HTML, a CID image, and a PDF. The helper provides direct APIs for all of those components.

When a strict MIME contract with another system is required, verify the helper-generated tree via raw source or a parser. If the actual structure does not match the contract, switch to creating multiparts directly.

## 5. When Should You Create Multipart Directly?

Use Jakarta Mail directly when you need granular control that the helper does not express conveniently.

Common scenarios:

### 5.1. Needing an Exact Nested MIME Tree

For example, the receiver requires:

```text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── multipart/related
│       ├── text/html
│       └── image/png; Content-ID: <logo>
└── application/pdf; attachment
```

In this tree, the HTML and related image branch is an alternative version to plain text. The related branch sits inside alternative. If the helper builds a different nesting shape from the contract, Jakarta Mail lets you construct the exact parent-child relationship.

### 5.2. Needing Specialized Multipart Subtypes

Examples:

- `multipart/report` for delivery status notifications.
- `multipart/signed` for a digitally signed MIME structure.
- `multipart/alternative` at root per integration requirements.
- A specialized multipart subtype expected by the receiving system.

The helper has predefined modes, not a general-purpose API for passing arbitrary multipart subtypes or parameters.

### 5.3. Needing Control Over Individual Part Headers

You may need to manually set:

- `Content-Type` with parameters such as `method=REQUEST` for a calendar part.
- `Content-ID` or `Content-Location`.
- `Content-Disposition` as inline or attachment.
- Filename, charset, and transfer encoding.
- `start` or `type` parameters of `multipart/related`.
- Custom headers specified in an integration contract.

Jakarta Mail allows direct manipulation of each `MimeBodyPart` and `MimeMultipart`. However, headers must conform to MIME standards and the actual semantics of the part.

### 5.4. Needing Parts Not Directly Supported by the Helper

An email may contain `text/calendar`, `message/rfc822`, or signed/encrypted content. These are not just ordinary attachments. They require exact content type, disposition, and placement inside the MIME tree.

### 5.5. Needing to Process Existing MIME Messages

If the application receives a MIME email and must wrap, forward, or build a new message from one of its parts, Jakarta Mail APIs provide finer-grained traversal and assembly of parts. Special care is needed to preserve signed content or threading headers.

## 6. Jakarta Mail Classes to Know

When building multiparts directly, the primary classes are:

| Class | Responsibility |
|---|---|
| `MimeMessage` | Complete email: headers and root content. |
| `MimeMultipart` | A group of multiple parts with a subtype such as mixed, related, or alternative. |
| `MimeBodyPart` | A single part with its own headers and content; can hold text, binary, or nested multipart. |
| `DataHandler` | Supplies data to a body part via a DataSource. |
| `DataSource` | Source of bytes and content type for a part. |
| `ByteArrayDataSource` | Convenient DataSource for byte data already in memory. |
| `Part` | API/constants for disposition, such as INLINE and ATTACHMENT. |
| `InternetAddress` | Represents an Internet email address. |

With Spring Boot using Spring Framework 6, mail packages live in the `jakarta.mail` namespace. Older Spring projects may use `javax.mail`; never mix both namespaces in the same application. Dependencies and Jakarta Mail/Activation versions must be compatible with the Spring version in use.

## 7. How to Create Multipart Directly

General workflow:

1. Create `MimeMessage` via `JavaMailSender.createMimeMessage()` to use the configured mail session.
2. Set From, To, Subject, and necessary headers.
3. Create each leaf `MimeBodyPart`.
4. Set content type, charset, Content-ID, and disposition for each part.
5. Create `MimeMultipart` groups by subtype.
6. Nest groups by setting a multipart as the content of a body part.
7. Attach the root multipart to the message via `message.setContent(...)`.
8. Send the message via `JavaMailSender.send(...)`.

The key is building the tree bottom-up from leaf parts to the root. Every multipart group should have a clear semantic purpose.

### 7.1. Creating an Email with Only Plain Text and HTML

If you want the root to be `multipart/alternative`:

```java
MimeMessage message = mailSender.createMimeMessage();

message.setFrom(new InternetAddress("notice@example.org"));
message.setRecipients(
        Message.RecipientType.TO,
        InternetAddress.parse(recipient, true)
);
message.setSubject("Notification", "UTF-8");

MimeBodyPart plainPart = new MimeBodyPart();
plainPart.setText(
        "Your request has been received.",
        "UTF-8"
);

MimeBodyPart htmlPart = new MimeBodyPart();
htmlPart.setContent(
        "<html><body><h1>Your request has been received.</h1></body></html>",
        "text/html; charset=UTF-8"
);

MimeMultipart alternative = new MimeMultipart("alternative");
alternative.addBodyPart(plainPart);
alternative.addBodyPart(htmlPart);

message.setContent(alternative);

mailSender.send(message);
```

In `multipart/alternative`, ordering usually puts the simpler form first and the richer form second. In this example, plain text precedes HTML.

### 7.2. Creating a mixed → alternative → related Tree

Suppose the email needs:

- Plain text.
- HTML with an inline logo.
- PDF attachment.

Target tree:

```text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── multipart/related
│       ├── text/html
│       └── image/png; Content-ID: <brand-logo>
└── application/pdf; attachment
```

Illustrative code:

```java
import jakarta.activation.DataHandler;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Part;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeMultipart;
import jakarta.mail.util.ByteArrayDataSource;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public void sendCustomReport(String recipient)
        throws MessagingException, IOException {

    MimeMessage message = mailSender.createMimeMessage();

    message.setFrom(new InternetAddress("reports@example.org"));
    message.setRecipients(
            Message.RecipientType.TO,
            InternetAddress.parse(recipient, true)
    );
    message.setSubject("Monthly Report", StandardCharsets.UTF_8.name());

    // 1. Plain text is the simple content option.
    MimeBodyPart plainPart = new MimeBodyPart();
    plainPart.setText(
            "The monthly report is ready. See the attached PDF.",
            StandardCharsets.UTF_8.name()
    );

    // 2. HTML is the root of the related branch.
    String cid = "brand-logo";

    MimeBodyPart htmlPart = new MimeBodyPart();
    htmlPart.setContent(
            "<html><body>"
                    + "<h1>Monthly Report</h1>"
                    + "<img src=\"cid:" + cid + "\" alt=\"Logo\">"
                    + "<p>See the attached PDF file.</p>"
                    + "</body></html>",
            "text/html; charset=UTF-8"
    );

    // 3. Image referenced via CID from HTML.
    byte[] logoBytes = loadLogoBytes();

    MimeBodyPart logoPart = new MimeBodyPart();
    logoPart.setDataHandler(new DataHandler(
            new ByteArrayDataSource(logoBytes, "image/png")
    ));
    logoPart.setHeader("Content-ID", "<" + cid + ">");
    logoPart.setDisposition(Part.INLINE);

    MimeMultipart related = new MimeMultipart("related");
    related.addBodyPart(htmlPart);
    related.addBodyPart(logoPart);

    // 4. Wrap HTML + image together as one alternative body part.
    MimeBodyPart htmlAlternativePart = new MimeBodyPart();
    htmlAlternativePart.setContent(related);

    MimeMultipart alternative = new MimeMultipart("alternative");
    alternative.addBodyPart(plainPart);
    alternative.addBodyPart(htmlAlternativePart);

    MimeBodyPart mainBodyPart = new MimeBodyPart();
    mainBodyPart.setContent(alternative);

    // 5. PDF is an independent attachment.
    byte[] pdfBytes = loadReportBytes();

    MimeBodyPart pdfPart = new MimeBodyPart();
    pdfPart.setDataHandler(new DataHandler(
            new ByteArrayDataSource(pdfBytes, "application/pdf")
    ));
    pdfPart.setFileName("monthly-report.pdf");
    pdfPart.setDisposition(Part.ATTACHMENT);

    // 6. Mixed root groups the body and attachment.
    MimeMultipart mixed = new MimeMultipart("mixed");
    mixed.addBodyPart(mainBodyPart);
    mixed.addBodyPart(pdfPart);

    message.setContent(mixed);

    mailSender.send(message);
}
```

`loadLogoBytes()` and `loadReportBytes()` are illustrative functions reading image/PDF data from an application-managed source. They must return valid bytes and be completely readable before sending.

The MIME tree is explicitly controlled:

- `mixed` at the root holds the main body and PDF.
- `alternative` lets the client pick plain or the HTML version.
- `related` groups HTML and the image HTML references.
- The image's `Content-ID` matches the CID URL in HTML.

This example shows why the direct API is chosen: the application wants to mandate explicitly that the related branch is an element inside alternative.

## 8. Creating Attachments and Inline Parts Directly

With the low-level API, you are responsible for setting each part's headers.

### Attachment from Byte Array

```java
MimeBodyPart attachment = new MimeBodyPart();

attachment.setDataHandler(new DataHandler(
        new ByteArrayDataSource(pdfBytes, "application/pdf")
));

attachment.setFileName("invoice.pdf");
attachment.setDisposition(Part.ATTACHMENT);
```

### Inline Image from Byte Array

```java
MimeBodyPart image = new MimeBodyPart();

image.setDataHandler(new DataHandler(
        new ByteArrayDataSource(imageBytes, "image/png")
));

image.setHeader("Content-ID", "<invoice-logo>");
image.setDisposition(Part.INLINE);
```

### Text Parts with Explicit Charset

```java
MimeBodyPart plain = new MimeBodyPart();
plain.setText(plainText, "UTF-8");

MimeBodyPart html = new MimeBodyPart();
html.setContent(htmlText, "text/html; charset=UTF-8");
```

Binary data such as PDF or PNG must never be converted into UTF-8 strings. Keep raw bytes intact and let `DataHandler`/`DataSource` provide the proper content type for the MIME part.

### Choosing DataSource by Data Source

- `ByteArrayDataSource`: data already in a byte array.
- `FileDataSource`: data read from a file.
- Custom DataSource: data from storage or another system.

With stream sources, ensure streams can be re-opened if the library needs to read content multiple times. Do not close streams before message serialization finishes.

## 9. Comparing the Helper and Direct Multipart

| Criterion | MimeMessageHelper | Direct Jakarta Mail |
|---|---|---|
| Abstraction level | Higher, API tailored to common email needs. | Lower, direct operations on parts and multiparts. |
| Message-building code | Short and readable. | Longer, requires creating each part. |
| Plain + HTML | Provides `setText(plain, html)`. | Manually build `multipart/alternative`. |
| Inline resources | Provides `addInline(...)`. | Manually create body part, DataHandler, Content-ID, and related. |
| Attachments | Provides `addAttachment(...)`. | Manually create part, DataSource, filename, and disposition. |
| Multipart modes | Prebuilt modes available. | Manually pick subtypes and nested tree. |
| Per-part headers | Mostly managed by helper. | Direct control. |
| Specialized MIME structures | Limited by helper design. | More flexible. |
| Code volume | Less. | More. |
| Misconfiguration risk | Lower for common cases. | Higher since you manage metadata and relationships yourself. |
| Custom MIME contract fit | Depends on helper modes/APIs. | Ideal when exact structure is required. |
| Maintenance | Easier for standard needs. | Requires MIME knowledge and thorough testing. |

### Selection Matrix

| Requirement | How to start |
|---|---|
| Text-only or HTML-only | Helper |
| Plain text + HTML | Helper |
| HTML + a few CID images | Helper |
| Body + PDF/CSV attachment | Helper |
| HTML + CID + normal attachments | Helper with suitable mode |
| Root must be a specific multipart subtype | Direct multipart |
| Custom nested related/alternative tree per contract | Direct multipart |
| Calendar part with special MIME parameters | Direct multipart or specialized library |
| `message/rfc822` or special MIME part | Direct multipart |
| `multipart/signed` or S/MIME | Specialized S/MIME library and Jakarta Mail |
| Must preserve an incoming MIME message intact | Jakarta Mail, with a clear content-preservation workflow |

## 10. Can MimeMessageHelper Be Combined with Direct Multipart?

Technically, `MimeMessageHelper` operates on Jakarta Mail's `MimeMessage`. You can use the helper to set familiar headers and then attach a manually built MIME tree.

Example:

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setFrom("reports@example.org");
helper.setTo(recipient);
helper.setSubject("Report");

MimeMultipart customRoot = buildCustomMultipart();
message.setContent(customRoot);

mailSender.send(message);
```

This can be convenient if you want the helper for From/To/Subject while still building the body manually. However, understand an important limitation: the helper may hold references to the multipart it initialized. If you later replace root content with another tree, subsequent body API calls on the helper may operate on the old tree.

Avoid this pattern:

```java
MimeMessageHelper helper = new MimeMessageHelper(message, true);

helper.setText("Initial body");

// Replace root with custom MIME tree.
message.setContent(customRoot);

// Do not continue assuming the helper manages customRoot.
helper.addAttachment("report.pdf", resource);
```

After replacing the root, do not call `setText`, `addInline`, or `addAttachment` on the helper to continue building the body. Once control of the structure moves to direct Jakarta Mail, let the direct code own the entire MIME body of that message.

**Recommendation:** pick one mechanism responsible for building the body of each message. You may use the helper to set headers before attaching a custom root, but do not split body editing between the two mechanisms.

## 11. Setting Headers, Charset, and Encoding When Creating Multipart Directly

When using the helper, many of these details are handled via constructors and APIs. When creating directly, pay attention to:

### Subject

Use the charset overload:

```java
message.setSubject(subject, "UTF-8");
```

This ensures subjects with Unicode characters are encoded properly per Jakarta Mail.

### Text Body

Use an explicit charset:

```java
plainPart.setText(plainText, "UTF-8");
```

### HTML Body

Set content type with charset:

```java
htmlPart.setContent(html, "text/html; charset=UTF-8");
```

### Binary Parts

Declare the right MIME type:

```java
new ByteArrayDataSource(pdfBytes, "application/pdf")
new ByteArrayDataSource(pngBytes, "image/png")
```

Never use UTF-8 to convert PDF or image bytes into text. The mail library serializes binary parts with an appropriate transfer encoding.

### Boundaries

Do not concatenate boundaries into MIME strings manually. `MimeMultipart` manages boundaries automatically during serialization. Building raw MIME via strings easily causes bugs in line breaks, closing boundaries, nested multiparts, and encoding.

## 12. Inspecting the Generated MIME Tree

Whether using the helper or direct APIs, do not just read code and guess what shape the message will take. Inspect raw MIME or parse the part tree.

You can serialize the message to an output stream in a test environment:

```java
ByteArrayOutputStream output = new ByteArrayOutputStream();

message.saveChanges();
message.writeTo(output);

String raw = output.toString(StandardCharsets.UTF_8);
```

`saveChanges()` finalizes headers before inspecting source. In normal Spring sending flows, the sender/transport handles necessary finalization steps; not every service needs to call it manually before `send`.

When inspecting raw source, check for:

- `MIME-Version`.
- `Content-Type` at root and nested multiparts.
- `boundary` of each group.
- Part order in alternative.
- Whether HTML and images sit inside related as expected.
- Whether `Content-ID` matches CID URLs.
- Whether attachments have `Content-Disposition: attachment` and appropriate filenames.
- Charset and transfer encoding.

Never log full raw emails in production because they can contain addresses, personal data, tokens, and attachments.

### Traversing the Part Tree with Jakarta Mail

A simple utility:

```java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.MessagingException;
import java.io.IOException;

public final class MimeTreeInspector {

    private MimeTreeInspector() {}

    public static void print(Part part, String indent)
            throws MessagingException, IOException {

        System.out.println(
                indent + "Content-Type: " + part.getContentType()
        );
        System.out.println(
                indent + "Disposition: " + part.getDisposition()
        );
        System.out.println(
                indent + "Filename: " + part.getFileName()
        );

        String[] contentIds = part.getHeader("Content-ID");
        if (contentIds != null) {
            for (String contentId : contentIds) {
                System.out.println(indent + "Content-ID: " + contentId);
            }
        }

        Object content = part.getContent();

        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                print(child, indent + "  ");
            }
        }
    }
}
```

Call:

```java
MimeTreeInspector.print(message, "");
```

For the custom tree in the earlier example, conceptual output:

```text
multipart/mixed
  multipart/alternative
    text/plain; charset=UTF-8
    multipart/related
      text/html; charset=UTF-8
      image/png; Content-ID: <brand-logo>; inline
  application/pdf; attachment; filename=monthly-report.pdf
```

This verifies the actual structure rather than relying on assumptions from code. `getContent()` can read part data and throw I/O errors; use this utility only in controlled inspections.

## 13. Testing When Using the Helper vs. Direct Multipart

Both approaches must be tested toward the same goal: the message has the right content and the right MIME tree.

### Unit Tests for the Helper

You can build a message without connecting to SMTP:

1. Create `MimeMessage` via the sender.
2. Use `MimeMessageHelper` to build the body.
3. Serialize or traverse the MIME tree.
4. Check text, HTML, CID, attachments, and headers.

Example checking basic markers:

```java
@Test
void helperBuildsHtmlMailWithInlineLogo() throws Exception {
    MimeMessage message = mailSender.createMimeMessage();

    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            "UTF-8"
    );

    helper.setTo("user@example.net");
    helper.setSubject("CID test");
    helper.setText(
            "<html><body><img src=\"cid:logo-test\"></body></html>",
            true
    );
    helper.addInline(
            "logo-test",
            new ClassPathResource("mail/logo.png"),
            "image/png"
    );

    message.saveChanges();

    ByteArrayOutputStream output = new ByteArrayOutputStream();
    message.writeTo(output);
    String raw = output.toString(StandardCharsets.UTF_8);

    assertThat(raw).contains("multipart/related");
    assertThat(raw).contains("cid:logo-test");
    assertThat(raw).contains("Content-ID: <logo-test>");
}
```

In real tests, parse MIME to verify headers and part tree rather than only searching substrings, since headers may fold across lines and serialization formatting can vary.

### Unit Tests for Direct Multipart

For a custom builder, verify:

- Root has the right subtype.
- Child part count is right.
- Alternative order is right.
- HTML part and image part sit in the same related subtree.
- CID and Content-ID match.
- PDF resides in the outermost mixed branch.
- Charset and disposition are right.

Verifying the structure matters more than merely asserting `message.setContent(...)` was called.

### Integration Tests with a Mock SMTP Server

You can use Mailpit or GreenMail to confirm the sender delivered the message to a test SMTP server. After receiving the message, re-parse and inspect the MIME tree. This additionally verifies the path through transport.

A test SMTP server does not guarantee Gmail, Outlook, or Apple Mail will all render identically. For critical emails, test on target mail clients.

## 14. Common Mistakes When Creating Multipart Manually

| Error | Consequence | Fix |
|---|---|---|
| Forgetting to attach root multipart to message | Message lacks expected body | Call `message.setContent(rootMultipart)`. |
| Setting wrong subtype | Client misinterprets part relationships | Choose mixed, related, alternative by content semantics. |
| Reversing alternative order | Client may select unintended content | Place plain text first, HTML second. |
| CID image not in related with HTML | Client fails to resolve inline resource as expected | Nest HTML and image inside the same related subtree. |
| CID and Content-ID differ | Image fails to appear | Generate ID once and use it in both places. |
| Forgetting attachment disposition/filename | Client misclassifies file | Set `Part.ATTACHMENT` and filename. |
| Applying charset to binary data | File gets corrupted | Keep raw bytes and use DataSource with matching MIME type. |
| Building boundaries with strings | Malformed MIME | Let `MimeMultipart` generate and manage boundaries. |
| Single-read stream source | Error during serialize/send | Use a re-openable stream source or byte array. |
| Replacing root then calling helper body APIs | Calls may mutate the old multipart | Pick a single owner for building the body. |
| Not inspecting MIME source | Hard to pinpoint where bugs occur | Serialize/parse and inspect the part tree. |
| Assuming SMTP accepted means client renders right | Display bugs go unnoticed | Inspect raw MIME and real clients. |

## 15. Email Types That Should Use Specialized Libraries

Some MIME subtypes involve protocols or security. Creating a `MimeMultipart` with the right subtype alone does not guarantee a valid message.

### Calendar Invitations

`text/calendar` can contain iCalendar data with a `METHOD` such as REQUEST or CANCEL. For meeting invitations to work, you must produce VCALENDAR/VEVENT data conforming to the schema and properties like UID, DTSTART, DTEND, ORGANIZER, and ATTENDEE. You can use Jakarta Mail to attach the part, but use a dedicated iCalendar library to generate the calendar payload.

### S/MIME Signed/Encrypted

`multipart/signed` and other S/MIME formats require standards-compliant signing/encryption. You cannot simply add a signature file into mixed and consider the email signed. Use a dedicated S/MIME library and follow proper signing/verification workflows.

### Delivery Status Notifications

`multipart/report` has dedicated parts and parameters for delivery status reporting. It is not another way of naming an email with multiple attachments. When generating DSNs, follow the standard and mail transport capabilities.

In these cases, the helper may still be useful for content before entering a specialized pipeline, yet it does not replace protocol or cryptographic implementations.

## 16. Performance and Resource Management

Both the helper and direct Jakarta Mail ultimately produce a MIME message and serialize content when sending. Low-level APIs do not automatically make emails smaller or send faster.

Factors to consider:

- Large images/PDFs can increase heap usage when read entirely into byte arrays.
- MIME transfer encodings like base64 make transmitted payloads larger than the original binary data.
- Overly large HTML templates or too many inline resources increase render and serialization time.
- Custom DataSources must provide stable data throughout the send duration.
- Create a new `MimeMessage` per send; avoid sharing mutable messages across concurrent requests.
- Limit total size and attachment count per SMTP provider policies.

Using the helper reduces MIME boilerplate; using direct APIs gives finer control without replacing size and resource management.

## 17. Separating Message Builders from Business Logic

When an application has many email types, avoid letting each service assemble MIME trees differently.

You can organize:

```text
Business service
    |
    v
Email content model
    |
    v
Message builder
    ├── CommonMailBuilder (MimeMessageHelper)
    └── SpecialMimeBuilder (Jakarta Mail)
    |
    v
JavaMailSender
    |
    v
SMTP
```

`CommonMailBuilder` creates standard emails using the helper. `SpecialMimeBuilder` handles structures needing direct control. Both return a `MimeMessage` for a shared sending layer.

Interface example:

```java
public interface MailMessageBuilder<T> {

    MimeMessage build(T model) throws MessagingException;
}
```

A concrete builder can accept `JavaMailSender` and render/template dependencies. Separating builders ensures:

- Business services do not need to understand MIME.
- Header and charset rules remain consistent.
- Specialized structures are isolated and tested.
- Message construction can evolve without changing business workflows.
- Message types and content versions are easy to trace when investigating.

Do not build a complex builder framework for an application with only one email type. Separate layers when there are multiple message types or genuinely distinct MIME structures.

## 18. Decide by Requirements, Not Habit

Before writing code, determine:

1. How many bodies does the email have, and are they alternatives or coexisting?
2. Are there inline images/resources referenced by HTML?
3. Are there independent attachments?
4. Does the receiver require a specific MIME root or nested multipart?
5. Are there special subtypes or headers?
6. Are there signatures, encryption, calendar data, or specialized report formats?
7. Do you need strict control over part ordering and the related root?
8. Can the structure be verified with a raw MIME test?

If the answers revolve around standard text, HTML, inline images, and attachments, the helper usually works well. If there are specific structural or protocol requirements, create multiparts directly and test against the exact contract.

## 19. Takeaways

- **`MimeMessageHelper`** is the right choice for common emails: text, HTML, alternatives, inline resources, and attachments.
- Helper multipart modes include `NO`, `MIXED`, `RELATED`, and `MIXED_RELATED`; they cover standard structures.
- **Jakarta Mail `MimeMultipart` and `MimeBodyPart`** allow defining exact subtypes, ordering, and parent-child relationships for each part.
- Use direct multipart when a contract demands an exact MIME tree, specialized headers/parameters, or subtypes not conveniently supported by the helper.
- When building directly, you must manage Content-Type, charset, Content-ID, disposition, filename, DataSource, and multipart nesting yourself.
- For CID images, HTML and the image must sit in the same related branch; the ID in HTML must match Content-ID.
- For plain/HTML, use alternative and put the simpler form before the richer form.
- Do not mix helper body edits with manual root multipart replacement; designate one body owner per message.
- Use `JavaMailSender` to send messages whether the body was built with the helper or direct Jakarta Mail.
- Inspect raw MIME and parse the part tree; SMTP integration tests do not replace mail client display checks.
- Calendar, DSN, and S/MIME require protocol/signature compliance; setting a MIME subtype alone is not enough for validity.

Start with `MimeMessageHelper` for emails whose requirements its APIs express completely. When a system needs a **specialized MIME tree or part with an explicit contract**, use `MimeMultipart` and `MimeBodyPart` directly to control the structure, then send via `JavaMailSender` as usual. This separation keeps standard email code concise while managing special cases at the proper layer.
