# Nested MIME Structure Must Be Verified

A Spring Boot application sends an order confirmation email with three components: recipients need to read plain text content, the email has a nicer HTML presentation, and the HTML includes a logo displayed right inside the message. In addition, the email attaches a PDF invoice for the recipient to download. When using `MimeMessageHelper`, a developer may call `setText(plain, html)`, `addInline(...)`, and `addAttachment(...)` and then send the message. However, the fact that those calls do not throw an exception does not prove the email has the exact MIME structure the application expects.

**MIME is a hierarchical tree of email content parts.** A message can contain multiparts inside multiparts: an outer layer groups content groups, a related layer links HTML with inline images, and an alternative layer provides multiple representations of the same content. When sending multiple formats, you must understand and verify the **actual MIME tree** rather than only checking an HTML string or assuming an attachment sits at a fixed index.

In the **Multi-Format Sending** chapter of Spring Framework Mail, this lesson focuses on organizing nested multiparts, how Spring creates structures via `MimeMessageHelper`, and how to inspect the message with Jakarta Mail after serialization.

## 1. A MIME Message Is a Tree, Not a Single Body String

A simple email may have only a single body part:

```text
Content-Type: text/plain; charset=UTF-8

Hello, this is a notification email.
```

When an email has multiple content formats, MIME uses `multipart/*` types to group multiple parts:

| MIME type | Meaning |
|---|---|
| `multipart/mixed` | Groups independent parts in the same message, typically the email body and attachments. |
| `multipart/alternative` | Contains multiple alternative representations of the same content, such as plain text and HTML. |
| `multipart/related` | Groups main content with related resources, such as HTML and images referenced via CID. |
| `multipart/parallel` | Describes parts presented simultaneously; rarely used in typical transactional emails. |
| `multipart/digest` | Groups multiple messages in a digest structure. |

A `multipart` has multiple child parts. A child part can be text content, an image, a PDF, or another `multipart` itself. Therefore, a MIME message is a **hierarchical tree**.

Example of an email with plain text, HTML, an inline logo, and a PDF:

```text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain; charset=UTF-8
│   │   └── text/html; charset=UTF-8
│   └── image/png
│       ├── Content-ID: <company-logo>
│       └── Content-Disposition: inline
└── application/pdf
    ├── Content-Disposition: attachment
    └── filename: invoice-DH1024.pdf
```

This is the typical structure when using Spring's `MULTIPART_MODE_MIXED_RELATED` mode and adding an alternative body, an inline image, and an attachment. The exact structure may vary by multipart mode and message construction approach; what matters is that **the MIME relationships are correct**:

- Plain text and HTML are two representations of the same content.
- The logo image belongs to the related group and is referenced by HTML via CID.
- The PDF is an attachment independent of the HTML content.
- The outermost message holds the content groups to be sent together.

## 2. Understanding the Exact Role of Each Multipart

### 2.1. multipart/alternative: Multiple Representations of the Same Content

Example:

```text
Content-Type: multipart/alternative

--alternative-boundary
Content-Type: text/plain; charset=UTF-8

Order DH1024 has been confirmed.
View details: https://accounts.example.com/orders/DH1024

--alternative-boundary
Content-Type: text/html; charset=UTF-8

<p>Order <strong>DH1024</strong> has been confirmed.</p>
<p><a href="https://accounts.example.com/orders/DH1024">View details</a></p>

--alternative-boundary--
```

The two parts **are not two different notifications**. They convey the same content in two formats. Email clients generally select the most suitable format they can render.

According to MIME rules for `multipart/alternative`, parts are ordered from the less preferred/less rich form to the more preferred form. Therefore, the common order is:

1. `text/plain`.
2. `text/html`.

HTML is usually the richer choice and is therefore placed after plain text. Do not reverse the order arbitrarily without a specific compatibility reason.

### 2.2. multipart/related: Main Content and Related Resources

An HTML body references an image via CID:

```html
<p>Welcome to Example.</p>
<img src="cid:company-logo" alt="Example Logo">
```

MIME related groups HTML and the image:

```text
Content-Type: multipart/related

--related-boundary
Content-Type: text/html; charset=UTF-8

<p>Welcome to Example.</p>
<img src="cid:company-logo" alt="Example Logo">

--related-boundary
Content-Type: image/png
Content-ID: <company-logo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

[image data]
--related-boundary--
```

The HTML part is the main content; the image is a resource referenced by HTML. The CID in HTML must match the body part's `Content-ID`.

When an email has both plain text and HTML along with inline images, the main content part of related can be a `multipart/alternative`. Then the related tree contains the alternative, plus the image part.

### 2.3. multipart/mixed: Content and Independent Attachments

A PDF attachment is not a resource that HTML needs to reference. It is an independent part of the message:

```text
Content-Type: multipart/mixed

--mixed-boundary
Content-Type: text/plain; charset=UTF-8

Please see the attached invoice.

--mixed-boundary
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

[PDF data]
--mixed-boundary--
```

When combining multiple multipart types, mixed is usually the outermost layer to group the message body and attachments. A body part of mixed can itself be a related multipart or an alternative multipart.

## 3. Typical MIME Structure When Combining Multiple Formats

For an email consisting of plain text, HTML, an inline image, and a PDF attachment, the tree is typically organized as follows:

```text
multipart/mixed
│
├── multipart/related
│   │
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   │
│   └── image/png (inline, Content-ID: company-logo)
│
└── application/pdf (attachment)
```

Each layer resolves one relationship:

| Layer | Question resolved |
|---|---|
| Mixed | Which independent content groups are sent in the same message? |
| Related | Which resources belong to the main HTML content? |
| Alternative | In which formats can the recipient read the main content? |

Do not put a PDF into `multipart/related` just because it is sent in the same email. A PDF is not referenced by HTML via CID and has an independent download purpose, so it belongs in the attachment group.

## 4. Choosing the Right Multipart Mode in MimeMessageHelper

Spring `MimeMessageHelper` provides common multipart modes:

| Constant | Primary structure | When to use |
|---|---|---|
| `MULTIPART_MODE_NO` | No multipart created | Email has only a single simple body, no attachments/inline resources. |
| `MULTIPART_MODE_MIXED` | Root `multipart/mixed` | Content and attachments; no specialized related structure needed. |
| `MULTIPART_MODE_RELATED` | Root `multipart/related` | HTML content and associated inline resources. |
| `MULTIPART_MODE_MIXED_RELATED` | Mixed root with nested related | Email has related/inline content and independent attachments. |

### 4.1. Plain Text and HTML Only

If the email only needs two alternative bodies, use a multipart helper:

```java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(plainText, htmlText);
```

When there are no attachments or inline resources, the helper organizes content into an appropriate alternative structure. Inspect actual MIME if the application depends on a specific structure.

### 4.2. HTML and Inline Resources

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8");

helper.setText(plainText, htmlText);
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
```

Related mode fits when HTML references inline resources. If an independent attachment is needed in the same message, consider mixed-related so the attachment sits in the outer mixed layer.

### 4.3. HTML, Inline Images, and Attachments

This is the common case that needs verification:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setText(plainText, htmlText);
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
helper.addAttachment(
        "invoice-DH1024.pdf",
        new FileSystemResource(invoicePath),
        "application/pdf");
```

`MULTIPART_MODE_MIXED_RELATED` creates a mixed root and nested related container to group the main content with inline resources. Attachments are normally added to the mixed root.

**Call `setText(...)` before `addInline(...)`.** This order lets the helper set up the main content part before adding related resources.

### 4.4. Do Not Rely on the Boolean Constructor When Clear Structure Is Needed

The constructor:

```java
new MimeMessageHelper(message, true, "UTF-8")
```

enables multipart using the helper's default mode. When an email has multiple part types and its structure needs verification, explicitly specifying `MULTIPART_MODE_MIXED_RELATED` makes the intent clearer to readers and maintainers.

## 5. Complete Example of Creating a MIME Message

Suppose an email has:

- Plain text content.
- HTML content.
- An inline PNG logo.
- An attached PDF invoice.

Example:

```java
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.file.Path;

@Service
public class InvoiceMailSender {

    private final JavaMailSender mailSender;

    public InvoiceMailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            String orderCode,
            Path invoicePath) throws Exception {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Invoice for order " + orderCode);

        String plain = """
                EXAMPLE COMPANY

                The invoice for order %s is ready.
                Please see the attached PDF file.

                View order:
                https://accounts.example.com/orders/%s
                """.formatted(orderCode, orderCode);

        String html = """
                <html>
                  <body>
                    <p><strong>EXAMPLE COMPANY</strong></p>
                    <img src="cid:company-logo"
                         alt="Example Company Logo"
                         width="160">
                    <h1>Invoice Ready</h1>
                    <p>Order <strong>%s</strong>.</p>
                    <p>Please see the attached PDF file.</p>
                    <p>
                      <a href="https://accounts.example.com/orders/%s">
                        View order
                      </a>
                    </p>
                  </body>
                </html>
                """.formatted(orderCode, orderCode);

        helper.setText(plain, html);

        helper.addInline(
                "company-logo",
                new ClassPathResource("mail/images/logo.png"),
                "image/png");

        helper.addAttachment(
                "invoice-" + orderCode + ".pdf",
                new FileSystemResource(invoicePath),
                "application/pdf");

        mailSender.send(message);
    }
}
```

This is an example of MIME structure, not a complete production workflow. Real applications still need to validate the recipient, verify invoice access permissions, sanitize filenames/order codes, build URLs from a trusted base URL, ensure the file exists and is readable, and handle sending failures.

## 6. Part Order Matters

A MIME multipart is not an arbitrary list. Part order can affect how clients interpret the content.

### 6.1. Alternative: Plain Text First, HTML Second

`multipart/alternative` usually puts the plain text version first and the HTML version second:

```text
multipart/alternative
├── text/plain
└── text/html
```

The alternatives represent the same content. The later part is typically the richer/preferred format. Do not put a PDF attachment inside alternative thinking "if the client does not support HTML, download the PDF": an attachment is not an equivalent alternative representation of the body.

### 6.2. Related: Main Content and Referenced Resources

In `multipart/related`, the first part is typically the root content part, and subsequent parts are resources referenced by that content:

```text
multipart/related
├── multipart/alternative (main body)
└── image/png (CID resource)
```

If an inline image is not placed in the related group or the CID does not match, the client may fail to map the image into HTML as expected.

### 6.3. Mixed: Attachments Are Independent Parts

`multipart/mixed` groups the main content and attachments:

```text
multipart/mixed
├── multipart/related (main body + inline resources)
└── application/pdf (attachment)
```

Attachments normally do not need to be referenced from HTML. Clients display them in the attachment area or offer a file download action.

## 7. Why Must the Actual MIME Tree Be Verified?

Calling the helper methods properly is not enough to confirm the outcome. Bugs may only surface after the message is serialized:

- Attachment does not reside at the expected mixed layer.
- HTML and plain text do not belong together in an alternative body.
- Inline image is in the wrong group or its CID mismatches.
- MIME type or Content-Disposition is wrong.
- Attachment is missing because the resource was unreadable.
- Body parts are nested differently than tests assumed.
- Charset or filename encoding is wrong.

**Verifying the MIME tree** means reading the message after the helper has built it, traversing parts at every level, and checking content type, disposition, filename, Content-ID, and payload bytes.

Do not merely assert:

```java
assertThat(message.getContent()).isInstanceOf(Multipart.class);
```

That only confirms the outermost body is multipart. It does not prove the nested multiparts contain text/plain, text/html, inline images, and the PDF.

## 8. Traversing MIME Recursively with Jakarta Mail

Jakarta Mail provides the `Part` abstraction for a message or body part and `Multipart` for a container of parts. You can write a recursive traversal function to print the structure.

### 8.1. MIME Tree Printing Function

```java
import jakarta.mail.BodyPart;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

import java.io.IOException;

public final class MimeTreePrinter {

    private MimeTreePrinter() {}

    public static void print(Part part) throws MessagingException, IOException {
        print(part, 0);
    }

    private static void print(Part part, int depth)
            throws MessagingException, IOException {

        String indent = "  ".repeat(depth);
        String disposition = part.getDisposition();
        String filename = part.getFileName();
        String[] contentIds = part.getHeader("Content-ID");

        System.out.printf(
                "%s- type=%s; disposition=%s; filename=%s; contentId=%s%n",
                indent,
                part.getContentType(),
                disposition,
                filename,
                contentIds == null ? "" : String.join(",", contentIds));

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    BodyPart child = multipart.getBodyPart(i);
                    print(child, depth + 1);
                }
            }
        }
    }
}
```

The function takes `Part`, so it works on both `MimeMessage` (a message is also a Part) and child `BodyPart`s. It:

1. Prints Content-Type, disposition, filename, and Content-ID.
2. Checks whether the part is `multipart/*`.
3. Casts the content to `Multipart`.
4. Recursively traverses each child part.

`getContentType()` may include parameters such as `charset` or `boundary`. When checking MIME types, use `part.isMimeType("text/html")` or `part.isMimeType("multipart/related")` instead of comparing the full Content-Type string.

### 8.2. Expected Tree Output

For the example message, conceptual output may look like:

```text
- type=multipart/mixed; disposition=null; filename=null
  - type=multipart/related; disposition=null; filename=null
    - type=multipart/alternative; disposition=null; filename=null
      - type=text/plain; charset=UTF-8; disposition=null
      - type=text/html; charset=UTF-8; disposition=null
    - type=image/png; disposition=inline; filename=null; contentId=<company-logo>
  - type=application/pdf; disposition=attachment;
    filename=invoice-DH1024.pdf
```

This is illustrative output. Some providers/clients may produce different headers or structures, and Content-ID may be wrapped in angle brackets. What needs verification is that **the required parts exist and have the right relationships**, not that every header string matches an example character-for-character.

### 8.3. Traversing message/rfc822 When Needed

In some digest or forwarded emails, a body part may be `message/rfc822` containing another email. If the application needs to inspect nested messages as well, you can extend the traversal function to recognize that type and process its returned content when it is a `Part`.

For typical transactional emails with mixed/related/alternative, traversing `multipart/*` is usually sufficient. There is no need to implement nested-message handling if the business domain does not use it.

## 9. Verifying by Properties Rather Than Fixed Position

A common test bug is assuming:

```java
Multipart root = (Multipart) message.getContent();
BodyPart html = root.getBodyPart(0);
BodyPart pdf = root.getBodyPart(1);
```

That assumption holds only for one specific structure. When the helper creates nested multiparts, the first part can be another multipart rather than HTML directly. If the multipart mode changes, ordering and depth may shift.

Instead, verify **across the tree**:

- At least one `text/plain` part exists.
- At least one `text/html` part exists.
- An image part with the expected Content-ID exists.
- An attachment with the expected filename exists.
- The attachment has the appropriate MIME type.
- Attachment bytes match the source file.

### 9.1. Recursive MIME Type Search Function

```java
import jakarta.mail.BodyPart;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

import java.io.IOException;

public final class MimePartSearch {

    private MimePartSearch() {}

    public static boolean containsMimeType(
            Part part,
            String expectedMimeType)
            throws MessagingException, IOException {

        if (part.isMimeType(expectedMimeType)) {
            return true;
        }

        if (!part.isMimeType("multipart/*")) {
            return false;
        }

        Object content = part.getContent();
        if (!(content instanceof Multipart multipart)) {
            return false;
        }

        for (int i = 0; i < multipart.getCount(); i++) {
            BodyPart child = multipart.getBodyPart(i);
            if (containsMimeType(child, expectedMimeType)) {
                return true;
            }
        }
        return false;
    }
}
```

Usage:

```java
assertThat(MimePartSearch.containsMimeType(message, "text/plain")).isTrue();
assertThat(MimePartSearch.containsMimeType(message, "text/html")).isTrue();
assertThat(MimePartSearch.containsMimeType(message, "image/png")).isTrue();
assertThat(MimePartSearch.containsMimeType(message, "application/pdf")).isTrue();
```

This checks for the presence of MIME types. It does not yet prove the image has the right CID or that the PDF is an attachment. You still need to verify headers and content.

### 9.2. Searching for an Attachment by Filename

```java
public static boolean containsFilename(Part part, String expectedFilename)
        throws MessagingException, IOException {

    String filename = part.getFileName();
    if (expectedFilename.equals(filename)) {
        return true;
    }

    if (!part.isMimeType("multipart/*")) {
        return false;
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            if (containsFilename(
                    multipart.getBodyPart(i), expectedFilename)) {
                return true;
            }
        }
    }
    return false;
}
```

`getFileName()` is the filename metadata of the part. Depending on Jakarta Mail version and MIME configuration, decoding filename headers can be affected by compatibility properties. When testing Unicode names, check the result after serialize/parse on your actual library version.

### 9.3. Searching for Content-ID

```java
public static boolean containsContentId(Part part, String expectedId)
        throws MessagingException, IOException {

    String[] values = part.getHeader("Content-ID");
    if (values != null) {
        for (String value : values) {
            String normalized = value.trim();
            if (normalized.startsWith("<") && normalized.endsWith(">")) {
                normalized = normalized.substring(1, normalized.length() - 1);
            }
            if (expectedId.equals(normalized)) {
                return true;
            }
        }
    }

    if (!part.isMimeType("multipart/*")) {
        return false;
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            if (containsContentId(
                    multipart.getBodyPart(i), expectedId)) {
                return true;
            }
        }
    }
    return false;
}
```

The function above illustrates stripping angle brackets from the header. In real applications, handle headers according to MIME rules and avoid assuming every provider uses an identical representation.

## 10. Verifying Attachment Disposition and Bytes

Finding a filename alone is not enough. A part may have a filename with an inline disposition, or vice versa. When verifying a PDF attachment:

- `Content-Type` must match, such as `application/pdf`.
- `Content-Disposition` should be `attachment`.
- `filename` must be the expected name.
- Bytes after decoding transfer encoding must match the source file.

Example function to locate a part by filename:

```java
public static Part findPartByFilename(Part part, String expectedFilename)
        throws MessagingException, IOException {

    if (expectedFilename.equals(part.getFileName())) {
        return part;
    }

    if (!part.isMimeType("multipart/*")) {
        return null;
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            Part found = findPartByFilename(
                    multipart.getBodyPart(i), expectedFilename);
            if (found != null) {
                return found;
            }
        }
    }
    return null;
}
```

Then:

```java
Part pdfPart = findPartByFilename(message, "invoice-DH1024.pdf");

if (pdfPart == null) {
    throw new AssertionError("PDF attachment is missing");
}

if (!pdfPart.isMimeType("application/pdf")) {
    throw new AssertionError("Unexpected attachment MIME type");
}

if (!Part.ATTACHMENT.equalsIgnoreCase(pdfPart.getDisposition())) {
    throw new AssertionError("PDF is not marked as an attachment");
}
```

Some email clients or providers may handle disposition flexibly, yet when **the application explicitly creates an attachment**, expecting `Part.ATTACHMENT` is reasonable. If testing an email received from an external source, inspect both filename and Content-Disposition since not all clients attach identical metadata.

### 10.1. Reading Decoded Bytes

`Part.getInputStream()` returns the part content after Jakarta Mail handles Content-Transfer-Encoding:

```java
byte[] receivedBytes;
try (InputStream input = pdfPart.getInputStream()) {
    receivedBytes = input.readAllBytes();
}

byte[] sourceBytes = Files.readAllBytes(invoicePath);
assertThat(receivedBytes).containsExactly(sourceBytes);
```

This test snippet reads all bytes into memory, so it fits small fixtures. For large files, compare streams in buffered chunks or compute a streaming hash to avoid holding two large copies on the heap.

There is no need to Base64-decode again after `getInputStream()`. Jakarta Mail already decodes the MIME part's transfer encoding.

## 11. Serializing and Re-Parsing to Verify the Message

A helpful verification pattern is:

1. Build the message with `MimeMessageHelper`.
2. Call `saveChanges()` to finalize required headers.
3. Serialize the message to a byte stream with `writeTo(...)`.
4. Parse the byte stream into a new `MimeMessage`.
5. Traverse the MIME tree of the new message.

Re-parsing checks the structure that was actually serialized, not merely the in-memory object state before sending.

### 11.1. Round-Trip Example

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Properties;

Session session = Session.getInstance(new Properties());
MimeMessage original = new MimeMessage(session);

// Build the message and add parts via MimeMessageHelper here.

original.saveChanges();

ByteArrayOutputStream output = new ByteArrayOutputStream();
original.writeTo(output);

byte[] rawMessage = output.toByteArray();

MimeMessage parsed = new MimeMessage(
        session,
        new ByteArrayInputStream(rawMessage));

assertThat(MimePartSearch.containsMimeType(parsed, "text/plain")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "text/html")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "image/png")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "application/pdf")).isTrue();
```

The example uses the same `Session` to parse the freshly serialized message. In real tests, you can create a Session without SMTP configuration since the goal is only building and reading a MIME message.

### 11.2. Why Not Check Boundaries with Fixed Strings?

Each multipart has a generated boundary separating its parts. Boundaries may differ across message builds. Do not write:

```java
assertThat(rawText).contains("--boundary-123");
```

unless the test explicitly configures the boundary in a specialized fixture. Use the Jakarta Mail parser to traverse the MIME tree instead of depending on boundary strings.

### 11.3. Serialize Round-Trip Does Not Simulate an Email Client

A round-trip proves the message can be serialized and parsed into a readable MIME structure. It **does not prove** Gmail, Outlook, Apple Mail, or corporate webmail will render identically. Display also depends on the client, CSS support, image policies, proxies, and filters.

Therefore, maintain two types of verification:

- **MIME structural test:** checks part tree, headers, and bytes.
- **Client rendering test:** checks experience on target email clients.

## 12. Writing a Meaningful MIME Test

A test can construct a message with small fixtures and verify required properties.

### 12.1. Preparing Fixtures

```java
Path invoice = Files.createTempFile("invoice-", ".pdf");
byte[] pdfBytes = "%PDF-1.7 test document".getBytes(StandardCharsets.US_ASCII);
Files.write(invoice, pdfBytes);
```

Create a small PNG fixture or use a `ClassPathResource` available in test resources.

### 12.2. Building the Message

```java
Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Invoice DH1024");
helper.setText(
        "Invoice DH1024 is ready. See the attached file.",
        "<p>Invoice <strong>DH1024</strong> is ready.</p>"
                + "<img src=\"cid:company-logo\" alt=\"Logo\">");
helper.addInline(
        "company-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
helper.addAttachment(
        "invoice-DH1024.pdf",
        new FileSystemResource(invoice),
        "application/pdf");
```

### 12.3. Serializing and Verifying

```java
message.saveChanges();

ByteArrayOutputStream buffer = new ByteArrayOutputStream();
message.writeTo(buffer);

MimeMessage parsed = new MimeMessage(
        session,
        new ByteArrayInputStream(buffer.toByteArray()));

assertThat(MimePartSearch.containsMimeType(parsed, "text/plain")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "text/html")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "image/png")).isTrue();
assertThat(MimePartSearch.containsMimeType(parsed, "application/pdf")).isTrue();

assertThat(containsContentId(parsed, "company-logo")).isTrue();
assertThat(containsFilename(parsed, "invoice-DH1024.pdf")).isTrue();
```

`containsContentId` and `containsFilename` are the recursive traversal helpers shown earlier. The test should also verify that `invoice-DH1024.pdf` has attachment disposition and its bytes equal `pdfBytes`.

### 12.4. Verifying Relationships, Not Just Existence

If you only assert that text/plain, text/html, image/png, and application/pdf exist somewhere in the tree, the test may still miss cases where the image sits outside the related group or HTML fails to reference the right CID.

For a stricter structural test:

1. Verify root is `multipart/mixed` when using `MIXED_RELATED`.
2. Locate the `multipart/related` child.
3. Inside related, verify there is a `multipart/alternative` main body.
4. Inside alternative, verify `text/plain` and `text/html` exist.
5. Inside related, verify the image part has a CID matching HTML.
6. At the mixed root, verify the independent PDF attachment exists.

Do not apply these exact expectations to every multipart mode. Tests must match the structure the application intentionally chose.

## 13. Verification Function for Expected MIXED_RELATED Structure

The snippet below shows how to locate multipart levels by MIME type rather than fixed index. This is a test helper for the structure Spring builds with `MULTIPART_MODE_MIXED_RELATED`; if library versions or message construction approaches change, adapt to the actual MIME tree.

```java
import jakarta.mail.BodyPart;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MultipartNavigator {

    private MultipartNavigator() {}

    public static List<Part> childrenOf(Part part)
            throws MessagingException, IOException {

        List<Part> children = new ArrayList<>();
        if (!part.isMimeType("multipart/*")) {
            return children;
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                children.add(multipart.getBodyPart(i));
            }
        }
        return children;
    }

    public static Part firstChildOfType(Part parent, String mimeType)
            throws MessagingException, IOException {

        for (Part child : childrenOf(parent)) {
            if (child.isMimeType(mimeType)) {
                return child;
            }
        }
        return null;
    }
}
```

Level check example:

```java
assertThat(parsed.isMimeType("multipart/mixed")).isTrue();

Part related = MultipartNavigator.firstChildOfType(
        parsed, "multipart/related");
assertThat(related).isNotNull();

Part alternative = MultipartNavigator.firstChildOfType(
        related, "multipart/alternative");
assertThat(alternative).isNotNull();

assertThat(MimePartSearch.containsMimeType(
        alternative, "text/plain")).isTrue();
assertThat(MimePartSearch.containsMimeType(
        alternative, "text/html")).isTrue();
```

The example above assumes the related structure is a direct child of the mixed root. In another structure, recursive search may be needed instead of checking only direct children. That is why **printing the MIME tree before writing deep assertions** helps tests reflect real output accurately.

## 14. Verifying Headers and Charset

A MIME tree is not just part types; each part also carries its own headers.

### 14.1. Content-Type

Example:

```text
Content-Type: text/html; charset=UTF-8
```

Do not compare the entire string because parameter order or formatting may differ. Use:

```java
part.isMimeType("text/html")
```

and read the charset parameter when verification is needed:

```java
String contentType = part.getContentType();
```

Use an appropriate MIME type parser to read parameters; do not manually split strings on semicolons if full quoting handling is needed.

### 14.2. Content-Disposition

Attachments typically have:

```text
Content-Disposition: attachment; filename="invoice-DH1024.pdf"
```

Inline resources typically have:

```text
Content-Disposition: inline
```

Disposition is metadata hinting at presentation. Clients may still choose to display differently; outbound message tests should confirm the metadata generated by the application.

### 14.3. Content-ID

An inline part has the header:

```text
Content-ID: <company-logo>
```

HTML references:

```html
<img src="cid:company-logo" alt="Logo">
```

Both sides must be checked for matching. Do not only check that image/png exists; a PNG image without a matching CID cannot satisfy that HTML reference.

### 14.4. Charset and Vietnamese Content

Text bodies should use an explicit charset, typically UTF-8:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name());
```

Verify after serialize/parse that Vietnamese content is decoded properly. Do not glance at raw bytes and jump to conclusions; MIME transfer encoding and charset play distinct roles. For `text/plain` and `text/html`, check both the charset header and the content after Jakarta Mail reads the part.

## 15. Verifying MIME Using an SMTP Catcher

Serialize/parse unit tests check message structure inside the JVM. Integration tests with an SMTP catcher check the message actually sent by Spring to a test SMTP server.

Commonly used tools:

- **GreenMail:** mock SMTP/IMAP/POP3 server for Java integration tests.
- **Mailpit:** test SMTP server with a web UI to inspect emails.
- **MailHog:** SMTP sink for development/test environments.

Testing flow:

1. Start the SMTP catcher.
2. Configure Spring Boot to point to the test host/port.
3. Invoke the email sending service.
4. Retrieve the message from the catcher.
5. Parse the message and traverse the MIME tree.
6. Verify text/plain, text/html, inline CID, and attachments.

Example test configuration:

```yaml
spring:
  mail:
    host: localhost
    port: 1025
    username: ''
    password: ''
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
```

This is only an illustrative configuration for an SMTP catcher running locally on port 1025; actual settings depend on the tool and test environment.

**An SMTP catcher does not fully simulate Gmail, Outlook, or Apple Mail.** It verifies submission to a test server and allows raw MIME inspection; to verify final layout, you still need to test on target clients.

## 16. Why Not Verify by Searching Strings in Raw MIME?

A test might try:

```java
String raw = new String(rawMessage, StandardCharsets.ISO_8859_1);
assertThat(raw).contains("multipart/related");
assertThat(raw).contains("application/pdf");
```

This is useful for quick debugging, but weak as structural verification:

- Headers may be written with different casing.
- Content-Type parameter order may vary.
- MIME boundaries are generated dynamically.
- Headers may be folded across multiple lines.
- Unicode filenames may be encoded.
- Base64 content may be wrapped across lines.
- A MIME type string could appear inside body text rather than a part header.

Use the Jakarta Mail parser to verify **parsed structure and metadata**, and reserve raw MIME for investigating header/serialization details.

## 17. Security and Integrity of MIME Parts

MIME verification is not only for ensuring clients render properly; it also helps applications detect misplaced or missing data.

### 17.1. Do Not Trust User-Supplied Content-Type

If an uploaded file is sent as an attachment, do not treat `MultipartFile.getContentType()` as proof of content. MIME types must be determined from verified actual format and application policy.

### 17.2. Control Filenames

Attachment filenames must not contain paths, CR/LF, control characters, or sensitive information. Never use client-supplied filenames directly in headers.

### 17.3. Do Not Log Full Raw MIME in Production

Raw messages can contain:

- Personal email addresses.
- Transaction contents.
- Verification or password reset tokens.
- Attachments containing financial, medical, or record data.

Log only necessary metadata such as notification ID, template version, part count, MIME types, sizes, and error codes. When collecting raw MIME for debugging is necessary, enforce restricted access and appropriate retention periods.

### 17.4. A Valid MIME Structure Does Not Make HTML Content Safe

A message with completely valid nested multiparts can still contain HTML injection, phishing URLs, or inappropriate content. Escape dynamic data, validate URLs, and govern templates independently of MIME tree verification.

## 18. Common Mistakes When Creating and Verifying Nested MIME

### 18.1. Assuming Multipart Has Only One Level

Emails can contain mixed → related → alternative. Reading only the root multipart causes tests to miss nested parts. Traverse recursively.

### 18.2. Putting the PDF Inside alternative

A PDF attachment is not an alternative representation of the body. Place it in mixed as an independent part.

### 18.3. Putting Inline Images Outside related

HTML may fail to resolve CIDs if the related structure is not organized properly. Use related mode, or mixed-related when attachments are also present.

### 18.4. Mismatched CID

HTML references `cid:logo` while the helper adds `brand-logo`. Check both HTML and the Content-ID header.

### 18.5. Relying on Fixed Indices

Part indices can shift when adding inline resources, attachments, or changing multipart mode. Search by MIME type, filename, and Content-ID.

### 18.6. Forgetting setText Before addInline

Call `setText` before `addInline` per Spring's recommendation to establish the main content before attaching related resources.

### 18.7. Not Enabling Multipart

Attachments and inline resources require a multipart structure. Choose the right constructor/helper mode from the start.

### 18.8. Comparing Content-Type with Exact String Equality

`text/html; charset=UTF-8` and `text/html; charset="UTF-8"` are still the same MIME type. Use `isMimeType("text/html")`.

### 18.9. Checking Fixed Raw Boundaries

Boundaries vary per message. Parse MIME instead of searching for hardcoded boundary strings.

### 18.10. Assuming Serialize Round-Trip Proves Client Rendering

It only verifies MIME can be serialized and parsed. Separate client tests are needed to confirm rendering.

### 18.11. Checking Only MIME Type, Not Relationships

Having both image/png and text/html does not prove HTML references the right CID. Verify Content-ID and related grouping.

### 18.12. Checking Only Filename, Not Bytes

The filename may be right while the file is empty or corrupted. Compare bytes or hashes with the source in tests.

### 18.13. Treating Inline Attachments and Regular Attachments as Identical

Content-Disposition and CID relationships differ. Inline resources serve HTML; regular attachments serve file downloads.

## 19. Practice Exercises

### Exercise 1 — Draw the MIME Tree

An email has `text/plain`, `text/html`, two inline images, and one PDF attachment. Draw the appropriate MIME tree when using `MULTIPART_MODE_MIXED_RELATED`. Clearly indicate which parts belong to alternative, related, and mixed.

### Exercise 2 — Choose the Multipart Mode

Choose the mode for each case:

1. Only text/plain.
2. HTML and one CID logo.
3. Plain text + HTML + CID logo.
4. Plain text + HTML + CID logo + PDF attachment.

Explain why the fourth case fits `MULTIPART_MODE_MIXED_RELATED`.

### Exercise 3 — Write the Helper

Write Java code using `MimeMessageHelper` to build an email containing plain text, HTML, an inline logo, and a PDF file. Ensure HTML references a CID matching the ID passed to `addInline`.

### Exercise 4 — Recursive Traversal

Write a method taking `Part` that prints Content-Type, disposition, filename, and Content-ID. When the part is multipart, traverse all child parts. Explain why checking only the root is not enough.

### Exercise 5 — Verify Relationships

A message has `text/html` and `image/png`, yet the logo does not display. Design checks confirming:

- HTML has `src="cid:company-logo"`.
- The image part has Content-ID `company-logo`.
- The image part belongs to the related group.
- Image bytes are readable.

### Exercise 6 — Missing Attachment

A test only verifies that the root message is multipart and contains `application/pdf`. However, the PDF has no filename and its disposition is inline. Explain why the current test is insufficient and add assertions.

### Exercise 7 — Serialize Round-Trip

Build a message, call `saveChanges`, `writeTo`, parse into a new `MimeMessage`, and verify MIME types. Why should boundaries not be compared using fixed strings?

### Exercise 8 — Alternative Ordering

Explain why `text/plain` is normally placed before `text/html` in `multipart/alternative` and why a PDF does not belong in alternative.

### Exercise 9 — SMTP Catcher

Design an integration test sending a message to Mailpit or GreenMail, then fetching the message and inspecting the MIME tree. What does this test prove, and what does it not prove?

### Exercise 10 — Security

An attachment is labeled `Content-Type: application/pdf`, yet its bytes are not a PDF. Why does a valid MIME structure still not guarantee a safe file? Propose checks at the upload/storage layer.

## 20. Takeaways and References

When **nested MIME structure must be verified** in Spring Framework Mail:

1. View the message as a MIME tree; a multipart can contain other multiparts.
2. Use `multipart/alternative` for text/plain and text/html of the same content.
3. Use `multipart/related` to group HTML with inline images referenced via CID.
4. Use `multipart/mixed` to group content and independent attachments.
5. With plain + HTML + inline image + attachment, consider `MULTIPART_MODE_MIXED_RELATED`.
6. Call `setText` before `addInline` and ensure CIDs in HTML match part Content-IDs.
7. Traverse MIME recursively using `Part` and `Multipart`; do not rely on fixed part indices.
8. Check MIME types with `isMimeType`, while verifying disposition, filename, Content-ID, and payload bytes.
9. Serialize and re-parse the message to inspect the actual generated structure.
10. Separate structural tests from email client display testing.

Technical documentation worth consulting:

- **Spring Framework API — `MimeMessageHelper`:** multipart modes, `setText`, `addInline`, and `addAttachment`.
- **Spring Framework Reference — Email:** building MIME emails with `JavaMailSender` and `MimeMessageHelper`.
- **Jakarta Mail API — `Part`, `BodyPart`, `Multipart`, `MimeMessage`:** traversing and manipulating the MIME tree.
- **RFC 2045–2049 — Multipurpose Internet Mail Extensions:** MIME structure, body parts, and transfer encoding.
- **RFC 2046 — MIME Media Types:** `multipart/mixed`, `multipart/alternative`, `multipart/related`, and alternative ordering rules.
- **RFC 2387 — The MIME Multipart/Related Content-type:** grouping main content and related resources.
- **RFC 2392 — Content-ID and Message-ID Uniform Resource Locators:** referencing resources via `cid:`.

**Multi-format sending is more than just calling multiple setters.** The application must establish the proper relationships among alternative bodies, inline resources, and attachments; then verify the actual MIME tree using a parser. When verifying by structure and metadata instead of relying on part indices, tests become much more resilient to changes in templates, multipart modes, and providers.
