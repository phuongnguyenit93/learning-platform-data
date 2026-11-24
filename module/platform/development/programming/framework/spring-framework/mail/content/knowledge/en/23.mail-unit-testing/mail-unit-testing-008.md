# Testing Attachments, Inline Resources, and Content-ID

## 1. Unit testing goals in Spring Framework Mail

When an application sends emails with **Spring Framework Mail**, a notification may contain plain text, HTML, embedded inline images, and file attachments. Calling `JavaMailSender.send(...)` does not by itself prove the recipient will see the right file or the right image. Bugs can originate right at the **`MimeMessage` construction step**, before an SMTP server ever receives the email:

- A PDF was added as an inline image, or a logo image was attached as a file attachment.
- The `Content-ID` header does not match the `cid:...` value in HTML.
- The email contains two images yet both share the same Content-ID, making references ambiguous.
- Content-Type declares `image/png` while the resource payload is a different file type.
- The attachment filename is missing or corrupted after MIME encoding.
- The `text/plain` and `text/html` versions were not placed into the right `multipart/alternative` relationship.
- The resource is single-read, causing MIME serialization or a resend to fail.
- In tests, a mock confirms `send` was called without inspecting the email that was built.

Therefore, a solid test must inspect **the constructed MIME message**, not just method call counts. In this *Unit Testing* chapter, we primarily build emails **in memory**, use `MimeMessageHelper`, traverse the MIME tree, inspect headers, and read back binary payloads; no real SMTP server is needed for these checks.

### Expected outcomes

After practicing, you will be able to verify:

1. HTML content references the right image via `cid:logo`.
2. The image has the right `Content-Type`, matching `Content-ID`, and `Content-Disposition: inline`.
3. Attachments have a filename, `Content-Disposition: attachment`, and intact byte content.
4. `multipart/mixed`, `multipart/related`, and `multipart/alternative` structures represent the right relationships.
5. The email is not corrupted after `saveChanges()`, `writeTo(...)`, and re-parsing.
6. The mail-sending service actually passes the right `MimeMessage` to `JavaMailSender`, when tested with mocks/argument captors.
7. Common bugs are caught by meaningful assertions rather than relying solely on client rendering checks.

**Scope note:** Unit tests verify how the application builds messages. They do not prove SMTP delivery, DKIM/SPF, rendering in Gmail/Outlook, or that recipients can open attachment contents. Those require other test layers.

## 2. Understand the three MIME part types before writing assertions

A rich email typically has three groups:

| Group | Common MIME/Headers | Role |
|---|---|---|
| Main content | `text/plain` or `text/html` | Recipients read the message body |
| Inline resource | `image/png` or `image/jpeg`, `Content-ID`, `Content-Disposition: inline` | Referenced by HTML and displayed inside content |
| Attachment | `application/pdf`, `Content-Disposition: attachment`, filename | Standalone file for recipients to view or download |

MIME is a **tree**, not necessarily a flat list. A message with plain text, HTML, an inline logo, and a PDF attachment can be sketched as:

~~~text
MimeMessage: multipart/mixed
  |
  +-- multipart/related
  |     |
  |     +-- multipart/alternative
  |     |     |
  |     |     +-- text/plain; charset=UTF-8
  |     |     +-- text/html; charset=UTF-8
  |     |           <img src="cid:order-logo">
  |     |
  |     +-- image/png
  |           Content-ID: <order-logo>
  |           Content-Disposition: inline
  |
  +-- application/pdf
        Content-Disposition: attachment
        filename="invoice.pdf"
~~~

In Spring, `MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED` creates a mixed root with a related part inside it. Calling `setText(plainText, htmlText)` lets the helper build a multipart alternative as the content entry inside the related group.

Meaning of the subtypes:

- `multipart/alternative`: alternative representations of **the same content**, usually plain text before HTML.
- `multipart/related`: root content together with the resources referenced by that content.
- `multipart/mixed`: multiple independent parts of an email, usually combining body and attachments.

### Why not write `getBodyPart(0)` and `getBodyPart(1)` in every test?

With mixed-related, image parts live inside the related group, while attachments sit at the mixed level. Adding a `text/plain` part or a second image can change ordering and nesting depth. Assertions based solely on fixed indices break easily or inspect the wrong part.

A more durable strategy:

1. Check the root multipart type if it is part of the structural contract.
2. Traverse the MIME tree **recursively**.
3. Locate parts by `isMimeType(...)`, disposition, filename, or Content-ID.
4. Assert parsed/decoded values; avoid byte-for-byte matching on entire raw MIME because boundaries and encodings can vary.

## 3. How do inline resources and attachments differ?

Two calls that look similar for resources carry different semantics:

~~~java
helper.addInline(
        "order-logo",
        logoResource,
        "image/png");

helper.addAttachment(
        "invoice.pdf",
        invoiceResource,
        "application/pdf");
~~~

`addInline(...)` attaches a resource that HTML can reference. With Content-ID `order-logo`, the HTML tag uses:

~~~html
<img src="cid:order-logo" alt="Order logo">
~~~

`addAttachment(...)` adds an independent file, typically shown as a downloadable attachment in the email UI.

| Property to test | Inline image | PDF attachment |
|---|---|---|
| `Content-Type` | `image/png` | `application/pdf` |
| `Content-Disposition` | `inline` | `attachment` |
| `Content-ID` | Usually present, e.g., `<order-logo>` | Not required |
| `filename` | Not strictly required | Should match expected filename |
| HTML reference | `src="cid:order-logo"` | No CID reference needed |
| Payload | Intact PNG bytes | Intact PDF bytes |

**Content-ID is not a filename.** An image part with `Content-ID: <order-logo>` does not need the filename `order-logo.png`. Likewise, a PDF named `invoice.pdf` should not be treated as inline merely because a viewer can display it.

### Headers use angle brackets while HTML does not

Typically:

~~~mime
Content-ID: <order-logo>
~~~

In HTML:

~~~html
<img src="cid:order-logo">
~~~

When calling Spring:

~~~java
helper.addInline("order-logo", logoResource, "image/png");
~~~

The Content-ID argument is `order-logo`; do not pass `cid:` or `< >` into the call. The helper builds the matching header. In tests, normalize angle brackets around the header value when comparing semantically.

## 4. Distinguish unit tests, MIME round-trip tests, and SMTP integration tests

Testing can be split into three levels:

| Level | Operations | Verifies |
|---|---|---|
| In-memory unit test | Create `MimeMessage`, use helper, traverse parts | MIME construction logic and properties |
| MIME round-trip | `saveChanges` → `writeTo` → re-parse | Headers/body and bytes still read back cleanly after serialization |
| SMTP integration | Send to Mailpit/GreenMail/test SMTP sink | Message actually travels over SMTP transport and server receives it |

When the goal is **attachments, inline resources, and Content-ID**, most assertions can run without starting Spring Boot or an SMTP server. You can use a Jakarta Mail `Session` and `MimeMessage` directly inside JUnit.

A practical rule of thumb:

**Do not use an SMTP integration test to catch bugs a simple MIME unit test can catch. Equally, do not claim a MIME unit test proves email clients will render the image properly.**

## 5. Required dependencies

In a Spring Boot project with mail support:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-mail` typically provides Spring Mail and a Jakarta Mail implementation compatible with the active Spring Boot version. `spring-boot-starter-test` supplies JUnit Jupiter, AssertJ, Mockito, and common testing utilities per the starter configuration.

If the project does not use Spring Boot, declare compatible versions of `spring-context-support`, Jakarta Mail API/implementation, and test libraries. With Spring Framework 6+, packages are `jakarta.mail.*`; Spring Framework 5 or older projects typically use `javax.mail.*`. Never mix incompatible package namespaces in the same example.

Examples use Java 17+, JUnit Jupiter, and AssertJ. With Maven, declare the equivalent dependencies in `pom.xml`.

## 6. Create a fixture with text, HTML, image, and attachment

A good fixture uses **controlled bytes** so that after MIME encoding/decoding you can compare them accurately. In structural unit tests, fixed byte arrays work well; when testing whether real images/PDFs open, use genuinely valid file fixtures.

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class TestMailFactory {
    private TestMailFactory() {
    }

    public static final byte[] LOGO_BYTES =
            new byte[] {0x12, 0x34, 0x56, 0x78};
    public static final byte[] PDF_BYTES =
            new byte[] {0x25, 0x50, 0x44, 0x46, 0x2D};

    public static MimeMessage message() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("orders@example.test");
        helper.setTo("customer@example.test");
        helper.setSubject("Order ORD-001 confirmation");

        String plain = "Order ORD-001 has been confirmed.";
        String html = """
                <!doctype html>
                <html lang="en">
                  <body>
                    <img src="cid:order-logo"
                         alt="Order logo">
                    <p>Order <strong>ORD-001</strong>
                       has been confirmed.</p>
                  </body>
                </html>
                """;

        // Set body first, related resources afterward.
        helper.setText(plain, html);
        helper.addInline(
                "order-logo",
                new ByteArrayResource(LOGO_BYTES),
                "image/png");
        helper.addAttachment(
                "invoice-ORD-001.pdf",
                new ByteArrayResource(PDF_BYTES),
                "application/pdf");

        return message;
    }
}
~~~

In the fixture:

- `setText(plain, html)` creates both body versions.
- `addInline` creates the image part referenced by CID.
- `addAttachment` adds the PDF as an independent file.
- `ByteArrayResource` supplies in-memory data and can open fresh `InputStream` instances whenever needed.
- SMTP is never called; `MimeMessage` is built solely for testing.

The `LOGO_BYTES` and `PDF_BYTES` arrays are illustrative data, **not valid PNG/PDF files**. They are suited for testing byte preservation and headers, not rendering or opening files in email clients. When testing end-user rendering, use valid PNG/PDF fixtures.

### Why choose ByteArrayResource?

Jakarta Mail may read the resource when creating a `DataHandler`, during `saveChanges`, during serialization, or when sending. `ByteArrayResource` keeps bytes immutable and provides re-readable streams, ideal for unit tests.

Avoid wrapping a **one-shot** stream in `InputStreamResource` for attachments when building/serializing may read multiple times. For real files, use `ClassPathResource` or a source supplying a fresh stream per read.

## 7. Build a MIME tree traversal utility to inspect every part

A simple unit test might read one `Multipart` and grab each `BodyPart`. Yet with `MULTIPART_MODE_MIXED_RELATED`, HTML and inline images sit inside nested multiparts. Thus a recursive traversal test helper is essential.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MimeTree {
    private MimeTree() {
    }

    public static List<Part> allParts(Part root)
            throws MessagingException, IOException {
        List<Part> parts = new ArrayList<>();
        walk(root, parts);
        return parts;
    }

    private static void walk(Part part, List<Part> parts)
            throws MessagingException, IOException {
        parts.add(part);

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    walk(multipart.getBodyPart(i), parts);
                }
            }
        }
    }

    public static Part requireMimeType(
            Part root, String mimeType) throws Exception {
        for (Part part : allParts(root)) {
            if (part.isMimeType(mimeType)) {
                return part;
            }
        }
        throw new AssertionError(
                "Missing MIME part: " + mimeType);
    }

    public static Part requireFilename(
            Part root, String filename) throws Exception {
        for (Part part : allParts(root)) {
            if (filename.equals(part.getFileName())) {
                return part;
            }
        }
        throw new AssertionError(
                "Missing attachment: " + filename);
    }

    public static Part requireContentId(
            Part root, String expectedId) throws Exception {
        for (Part part : allParts(root)) {
            if (expectedId.equals(contentId(part))) {
                return part;
            }
        }
        throw new AssertionError(
                "Missing Content-ID: " + expectedId);
    }

    public static String contentId(Part part)
            throws MessagingException {
        String[] headers = part.getHeader("Content-ID");
        if (headers == null || headers.length == 0) {
            return null;
        }

        String value = headers[0].trim();
        if (value.length() >= 2
                && value.startsWith("<")
                && value.endsWith(">")) {
            return value.substring(1, value.length() - 1);
        }
        return value;
    }
}
~~~

This utility:

- Collects the **root**, multipart groups, and leaf parts, allowing you to locate `multipart/related` and `multipart/alternative`.
- Calls `getContent()` only on multiparts, avoiding decoding entire attachments merely while walking the structure.
- Finds parts by MIME type, filename, or Content-ID instead of relying on fixed positions.
- Normalizes angle brackets around Content-ID when comparing.
- Does not blindly lowercase Content-ID values because they are reference identifiers, not header names.

If two images share the same Content-Type, `requireMimeType(..., "image/png")` only returns the first one. When testing multiple images, use `requireContentId` to distinguish them or add a helper returning all parts matching a MIME type. When multiple attachments share a filename, inspect the full list and application rules rather than assuming filenames are always unique.

### Why is checking only leaf parts still insufficient?

A flat `multipart/mixed` structure can contain HTML, PNG, and PDF yet fail to express that the PNG relates to the HTML. Leaf-part existence checks would pass, while some email clients could display the image as an attachment.

When structure is part of the composer's contract, tests should verify:

1. Root is mixed.
2. A related group exists.
3. The related group contains the HTML body and inline images.
4. The PDF attachment sits as an independent part under the mixed root.

In applications that do not lock down a specific tree layout, prefer semantic assertions; avoid coupling tests tightly to details that do not affect product requirements.

## 8. Unit test verifying inline image and Content-ID

Example test using the `TestMailFactory` fixture and `MimeTree` built above:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class InlineResourceTest {
    @Test
    void embedsLogoWithCorrectContentId() throws Exception {
        MimeMessage message = TestMailFactory.message();

        Part image = MimeTree.requireContentId(
                message, "order-logo");

        assertThat(image.isMimeType("image/png")).isTrue();
        assertThat(image.getDisposition())
                .isEqualToIgnoringCase(Part.INLINE);

        assertThat(image.getHeader("Content-ID"))
                .containsExactly("<order-logo>");

        byte[] decoded;
        try (var input = image.getInputStream()) {
            decoded = input.readAllBytes();
        }
        assertThat(decoded)
                .containsExactly(TestMailFactory.LOGO_BYTES);
    }
}
~~~

These assertions confirm:

- A MIME part exists with the exact Content-ID.
- Its MIME type is `image/png`.
- Its disposition is inline.
- The raw header has standard `< >` angle brackets.
- Reading the part through Jakarta Mail yields bytes matching the fixture.

`Part.getInputStream()` supplies content **after Content-Transfer-Encoding decoding** at the Jakarta Mail layer; thus even if the MIME body is Base64-encoded, you still compare against the original bytes. Never compare raw Base64 lines directly against input file bytes.

### Why find images by Content-ID?

If HTML contains:

~~~html
<img src="cid:order-logo">
<img src="cid:tracking-icon">
~~~

both resources may be `image/png`. Searching by `image/png` and taking the first part would not prove the logo has the right ID. Searching by Content-ID verifies the exact mapping email clients rely on.

### Do not assert only a substring in HTML

A test like:

~~~java
assertThat(html).contains("cid:order-logo");
~~~

is useful yet **insufficient**: HTML might reference that string while the MIME message lacks any part bearing that Content-ID. A complete test verifies both **the HTML reference** and **the matching part**.

## 9. Verify text/html references the right image

With the fixture above, locate the HTML body by MIME type and read `getContent()`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class HtmlReferenceTest {
    @Test
    void htmlReferencesExistingInlineImage() throws Exception {
        MimeMessage message = TestMailFactory.message();

        Part htmlPart = MimeTree.requireMimeType(
                message, "text/html");
        String html = (String) htmlPart.getContent();

        assertThat(html)
                .contains("src=\"cid:order-logo\"");

        Part matchingImage = MimeTree.requireContentId(
                message, "order-logo");
        assertThat(matchingImage.isMimeType("image/png")).isTrue();
        assertThat(matchingImage.getDisposition())
                .isEqualToIgnoringCase(Part.INLINE);
    }
}
~~~

This test verifies both sides of the relationship:

~~~text
HTML                                MIME part
src="cid:order-logo" -----------> Content-ID: <order-logo>
                                      |
                                      +-- Content-Type: image/png
                                      +-- Disposition: inline
~~~

### Is HTML formatting strict?

HTML strings may vary in whitespace, single/double quotes, and attribute ordering:

~~~html
<img alt="Logo" src='cid:order-logo'>
~~~

An assertion checking only `src="cid:order-logo"` can fail even when the HTML has identical meaning. For complex HTML templates, an HTML parser like Jsoup can extract `img[src]` and compare URIs; that is a solid option for **template** tests. There is no need to pull in an HTML parser just to assert a simple fixture.

### CID must carry the exact reference value

Never accept a test where HTML uses `cid:order-logo` while the part has `Content-ID: <logo>`; the email may be accepted by SMTP yet the image fails to appear. Equally, never swap `cid:` for an `https:` URL while claiming to test an **inline MIME resource**: remote images and CID images use completely different delivery models.

## 10. Attachment unit test: filename, disposition, Content-Type, and bytes

An attachment is not verified merely because `addAttachment` was called. Inspect the result inside `MimeMessage`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class AttachmentTest {
    @Test
    void attachesInvoiceAsIndependentPdf() throws Exception {
        MimeMessage message = TestMailFactory.message();

        Part pdf = MimeTree.requireFilename(
                message, "invoice-ORD-001.pdf");

        assertThat(pdf.isMimeType("application/pdf")).isTrue();
        assertThat(pdf.getDisposition())
                .isEqualToIgnoringCase(Part.ATTACHMENT);
        assertThat(pdf.getFileName())
                .isEqualTo("invoice-ORD-001.pdf");

        byte[] decoded;
        try (var input = pdf.getInputStream()) {
            decoded = input.readAllBytes();
        }
        assertThat(decoded)
                .containsExactly(TestMailFactory.PDF_BYTES);
    }
}
~~~

**Filename and disposition are two distinct properties.** A MIME part with filename `invoice.pdf` yet `Content-Disposition: inline` will not necessarily be treated as a regular attachment by email clients. Likewise, a part with disposition attachment and no filename may show up as "unnamed" or render inconsistently.

### Unicode filenames

If a file is named `hóa-đơn-đã-thanh-toán.pdf`, Jakarta Mail may encode the filename parameter using MIME-compatible mechanisms. Unit tests should inspect the **decoded value from `getFileName()`**:

~~~java
assertThat(pdf.getFileName())
        .isEqualTo("hóa-đơn-đã-thanh-toán.pdf");
~~~

Avoid hard-snapshotting the entire raw `Content-Disposition` header and demanding byte-for-byte equality across implementations and versions. Different libraries/providers may encode filenames in distinct valid ways.

### Content-Type is not proof of a valid file

`addAttachment(..., "application/pdf")` sets the media type supplied by the application. If the bytes are garbage, `isMimeType("application/pdf")` will still pass.

Distinguish:

1. **MIME assembly test:** verifies headers and bytes were preserved.
2. **Resource validation test:** verifies real file bytes are valid PDF/PNG per product standards.
3. **Email client test:** verifies files arriving in a mailbox can be downloaded/opened.

Never treat an illustrative byte array as a valid PDF file merely because it starts with `%PDF-`.

## 11. Verify exact placement of inline resources and attachments in the MIME tree

Checking that MIME parts exist is step one, yet when **client rendering compatibility** is the goal, parent–child relationships also matter. For example, having three leaf parts `text/html`, `image/png`, and `application/pdf` does not prove the image sits inside the related group.

With `MULTIPART_MODE_MIXED_RELATED` and the fixture from Section 6, a structural test can be written as:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class NestedMimeTreeTest {
    @Test
    void nestsInlineImageUnderRelatedAndPdfUnderMixed()
            throws Exception {
        MimeMessage message = TestMailFactory.message();

        assertThat(message.isMimeType("multipart/mixed"))
                .isTrue();

        Multipart mixed = (Multipart) message.getContent();
        assertThat(mixed.getCount()).isEqualTo(2);

        BodyPart relatedContainer = mixed.getBodyPart(0);
        assertThat(relatedContainer.isMimeType("multipart/related"))
                .isTrue();

        BodyPart pdf = mixed.getBodyPart(1);
        assertThat(pdf.isMimeType("application/pdf")).isTrue();
        assertThat(pdf.getDisposition())
                .isEqualToIgnoringCase(Part.ATTACHMENT);

        Multipart related =
                (Multipart) relatedContainer.getContent();
        assertThat(related.getCount()).isEqualTo(2);

        BodyPart alternativeContainer = related.getBodyPart(0);
        assertThat(
                alternativeContainer.isMimeType("multipart/alternative"))
                .isTrue();

        BodyPart logo = related.getBodyPart(1);
        assertThat(logo.isMimeType("image/png")).isTrue();
        assertThat(MimeTree.contentId(logo))
                .isEqualTo("order-logo");
    }
}
~~~

This test verifies **a specific structural contract** of the helper when mixed-related is selected with one image and one PDF. Adding a second image adds a part to the related group; adding a second attachment adds a part to the mixed root. Update assertions to match new contracts rather than treating specific `getCount()` values as universal MIME rules for every email.

### Verify the alternative structure

Continuing from `alternativeContainer`:

~~~java
Multipart alternative =
        (Multipart) alternativeContainer.getContent();

assertThat(alternative.getCount()).isEqualTo(2);
assertThat(alternative.getBodyPart(0).isMimeType("text/plain"))
        .isTrue();
assertThat(alternative.getBodyPart(1).isMimeType("text/html"))
        .isTrue();
~~~

In `multipart/alternative`, MIME convention orders content from least rich to richest, so plain text normally precedes HTML. `MimeMessageHelper.setText(plainText, htmlText)` manages building both alternatives. Never manually attach two bodies as independent attachments expecting mail clients to pick properly.

### When should you avoid locking down positions?

If the application switches libraries or changes multipart modes while preserving functionality, overly strict part-index assertions may break unnecessarily. A balanced model:

- **General functional tests:** verify every inline resource and attachment has the right content/headers.
- **Composer MIME contract tests:** verify the specific mixed-related tree when that structure is a requirement.
- **Integration/client tests:** verify how clients actually render.

## 12. MIME round-trip: serialize then re-parse

An in-memory `MimeMessage` may hold `DataHandler` objects and resources not yet encoded into raw MIME. Before sending, Jakarta Mail generates the required headers/encodings/boundaries. Therefore **serializing and re-parsing** is a stronger check than only reading the freshly built object.

~~~text
MimeMessageHelper
       |
       v
MimeMessage in RAM
       |
       v
saveChanges()
       |
       v
writeTo(OutputStream)
       |
       v
Raw RFC 822 / MIME bytes
       |
       v
new MimeMessage(Session, InputStream)
       |
       v
Verify multipart, Content-ID, decoded bytes
~~~

Example:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Properties;

public final class MimeRoundTrip {
    private MimeRoundTrip() {
    }

    public static MimeMessage serializeAndParse(
            MimeMessage original) throws Exception {
        original.saveChanges();

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        original.writeTo(out);

        Session parserSession =
                Session.getInstance(new Properties());
        return new MimeMessage(
                parserSession,
                new ByteArrayInputStream(out.toByteArray()));
    }
}
~~~

`saveChanges()` tells the message to finalize required headers and metadata. `writeTo(...)` writes the message out as an actual byte stream. The `MimeMessage(Session, InputStream)` constructor re-parses those bytes without connecting to SMTP.

### Test that content survives round-trip

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class MimeRoundTripTest {
    @Test
    void preservesInlineAndAttachmentAfterSerialization()
            throws Exception {
        MimeMessage parsed = MimeRoundTrip.serializeAndParse(
                TestMailFactory.message());

        assertThat(parsed.isMimeType("multipart/mixed"))
                .isTrue();

        Part logo = MimeTree.requireContentId(
                parsed, "order-logo");
        assertThat(logo.isMimeType("image/png")).isTrue();
        assertThat(logo.getDisposition())
                .isEqualToIgnoringCase(Part.INLINE);

        try (var input = logo.getInputStream()) {
            assertThat(input.readAllBytes())
                    .containsExactly(TestMailFactory.LOGO_BYTES);
        }

        Part pdf = MimeTree.requireFilename(
                parsed, "invoice-ORD-001.pdf");
        assertThat(pdf.isMimeType("application/pdf")).isTrue();
        assertThat(pdf.getDisposition())
                .isEqualToIgnoringCase(Part.ATTACHMENT);

        try (var input = pdf.getInputStream()) {
            assertThat(input.readAllBytes())
                    .containsExactly(TestMailFactory.PDF_BYTES);
        }
    }
}
~~~

Round-trip testing can catch bugs invisible when inspecting only the in-memory object, such as improperly encoded headers, dropped Content-IDs, unserializable MIME parts, or attachment sources that cannot re-open streams.

**Limitation:** Re-parsing a message does not prove the email was accepted by SMTP, nor does it prove the end client will display images automatically. It proves correctness within the scope of the active serializer/parser.

### Do not snapshot the entire raw MIME

A raw message contains random boundaries, Date/Message-ID headers, line wrapping, and implementation-dependent Base64 folding:

~~~mime
Content-Type: multipart/mixed;
 boundary="----=_Part_42_238230984.1780000000000"
~~~

Do not assert that **raw bytes of the entire email match a snapshot file identically** when the requirement is only attachments/CIDs. Instead, parse the message and compare properties and **decoded** bytes. Full snapshots can fail over functionally irrelevant details.

## 13. Test a real service using Mockito ArgumentCaptor

In applications, message-building code usually lives inside a service, for example:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class InvoiceMailService {
    private final JavaMailSender sender;

    public InvoiceMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice(
            String recipient,
            byte[] logo,
            byte[] invoicePdf) {
        MimeMessage message = sender.createMimeMessage();
        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                    StandardCharsets.UTF_8.name());

            helper.setFrom("orders@example.test");
            helper.setTo(recipient);
            helper.setSubject("Invoice ORD-001");
            helper.setText(
                    "Invoice ORD-001 attached.",
                    "<p><img src=\"cid:order-logo\">"
                            + "Invoice ORD-001 attached.</p>");
            helper.addInline(
                    "order-logo",
                    new ByteArrayResource(logo),
                    "image/png");
            helper.addAttachment(
                    "invoice-ORD-001.pdf",
                    new ByteArrayResource(invoicePdf),
                    "application/pdf");
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot compose invoice email", ex);
        }

        sender.send(message);
    }
}
~~~

In the code above, `JavaMailSender` is a dependency and `send(MimeMessage)` is called only after composition. Building MIME requires no SMTP connection before `send(...)` runs.

### Test capturing the message passed to the sender

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class InvoiceMailServiceTest {
    @Test
    void sendsMessageContainingExpectedPdfAndLogo()
            throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        Session session = Session.getInstance(new Properties());

        when(sender.createMimeMessage())
                .thenReturn(new MimeMessage(session));

        InvoiceMailService service =
                new InvoiceMailService(sender);

        service.sendInvoice(
                "customer@example.test",
                TestMailFactory.LOGO_BYTES,
                TestMailFactory.PDF_BYTES);

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);
        verify(sender).send(captor.capture());

        MimeMessage parsed = MimeRoundTrip.serializeAndParse(
                captor.getValue());

        assertThat(parsed.getSubject())
                .isEqualTo("Invoice ORD-001");

        Part logo = MimeTree.requireContentId(
                parsed, "order-logo");
        assertThat(logo.isMimeType("image/png")).isTrue();

        Part pdf = MimeTree.requireFilename(
                parsed, "invoice-ORD-001.pdf");
        assertThat(pdf.getDisposition())
                .isEqualToIgnoringCase(Part.ATTACHMENT);

        try (var input = pdf.getInputStream()) {
            assertThat(input.readAllBytes())
                    .containsExactly(TestMailFactory.PDF_BYTES);
        }
    }
}
~~~

With Mockito:

- `when(sender.createMimeMessage())` returns a real in-memory MimeMessage.
- `sender.send(...)` is mocked so **nothing is sent over the network**.
- `ArgumentCaptor` captures the exact message the service passed to the sender.
- `MimeRoundTrip` verifies the MIME outcome after serialization.

This combines **a service unit test** with real message-structure inspection. It is far stronger than:

~~~java
verify(sender).send(any(MimeMessage.class));
~~~

because plain verification proves only that the method was called, saying nothing about attachment contents or Content-ID.

## 14. Test when the application uses MimeMessagePreparator

Another Spring Mail style passes a `MimeMessagePreparator` lambda to `JavaMailSender.send(...)`:

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class PreparatorMailService {
    private final JavaMailSender sender;

    public PreparatorMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void send(String recipient, byte[] logoBytes) {
        sender.send(message -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");
            helper.setFrom("orders@example.test");
            helper.setTo(recipient);
            helper.setSubject("New notification");
            helper.setText(
                    "<img src=\"cid:status-icon\">"
                            + "<p>Order confirmed.</p>",
                    true);
            helper.addInline(
                    "status-icon",
                    new org.springframework.core.io.ByteArrayResource(
                            logoBytes),
                    "image/png");
        });
    }
}
~~~

In this style, the code building `MimeMessage` sits **inside the callback**. A default Mockito mock of `sender.send(preparator)` **does not run the callback automatically**. Therefore a test like:

~~~java
verify(sender).send(any(MimeMessagePreparator.class));
~~~

only confirms a preparator was passed, without proving it built the right message.

### Use Mockito Answer to execute the preparator on a real MimeMessage

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;

import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessagePreparator;

class PreparatorMailServiceTest {
    @Test
    void preparatorAddsInlineImageWithExpectedCid()
            throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        Session session = Session.getInstance(new Properties());
        AtomicReference<MimeMessage> prepared =
                new AtomicReference<>();

        doAnswer(call -> {
            MimeMessagePreparator preparator =
                    call.getArgument(0);
            MimeMessage message = new MimeMessage(session);
            preparator.prepare(message);
            prepared.set(message);
            return null;
        }).when(sender).send(any(MimeMessagePreparator.class));

        new PreparatorMailService(sender)
                .send("customer@example.test", TestMailFactory.LOGO_BYTES);

        MimeMessage message = MimeRoundTrip.serializeAndParse(
                prepared.get());

        Part logo = MimeTree.requireContentId(
                message, "status-icon");
        assertThat(logo.isMimeType("image/png")).isTrue();
        assertThat(logo.getDisposition())
                .isEqualToIgnoringCase(Part.INLINE);

        String html = (String) MimeTree.requireMimeType(
                message, "text/html").getContent();
        assertThat(html).contains("cid:status-icon");
    }
}
~~~

In this test, `doAnswer` creates a real message and calls `preparator.prepare(message)`, so the content is built just as when a real sender invokes the callback. The test opens no network connection. Any error occurring during preparation is thrown inside the test, surfacing composition bugs.

**Note the API difference:** if the service uses `send(MimeMessage)`, capture the message; if the service uses `send(MimeMessagePreparator)`, the mock must execute the callback before content can be inspected. Do not mix the two methods and assume identical mock setup works for both.

## 15. Verify multiple inline images and unique Content-IDs

An HTML template may use distinct logos, illustrations, and status icons:

~~~html
<header>
  <img src="cid:header-logo" alt="Logo">
</header>
<main>
  <img src="cid:order-status" alt="Order status">
</main>
~~~

Composer:

~~~java
helper.setText(html, true);

helper.addInline(
        "header-logo",
        new ByteArrayResource(headerLogoBytes),
        "image/png");

helper.addInline(
        "order-status",
        new ByteArrayResource(orderStatusBytes),
        "image/png");
~~~

Tests should never grab "the first PNG." Look them up by Content-ID:

~~~java
Part headerLogo = MimeTree.requireContentId(
        message, "header-logo");
Part orderStatus = MimeTree.requireContentId(
        message, "order-status");

assertThat(headerLogo).isNotSameAs(orderStatus);
assertThat(headerLogo.isMimeType("image/png")).isTrue();
assertThat(orderStatus.isMimeType("image/png")).isTrue();
~~~

### Detect duplicate Content-IDs

Two inline parts sharing the same Content-ID make references ambiguous. You can check all MIME parts:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import java.util.HashSet;
import java.util.Set;

Set<String> seenIds = new HashSet<>();
for (Part part : MimeTree.allParts(message)) {
    String contentId = MimeTree.contentId(part);
    if (contentId == null) {
        continue;
    }

    assertThat(seenIds.add(contentId))
            .as("Content-ID must be unique: %s", contentId)
            .isTrue();
}
~~~

This is a simple test rule for messages where the application requires unique Content-IDs. In complex MIME structures, `multipart/alternative` relationships or special compatibility mechanisms may need a different resolution policy; for standard newsletter/receipt inline resources, unique IDs are the clearest choice.

### Verify every reference in HTML has a MIME part

When a template has many images, a general test can extract `cid:...` references and match them against Content-IDs:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashSet;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

String html = (String) MimeTree.requireMimeType(
        message, "text/html").getContent();

Pattern cidPattern =
        Pattern.compile("cid:([A-Za-z0-9._-]+)");
Matcher matcher = cidPattern.matcher(html);

Set<String> referencedIds = new HashSet<>();
while (matcher.find()) {
    referencedIds.add(matcher.group(1));
}

assertThat(referencedIds)
        .containsExactlyInAnyOrder(
                "header-logo", "order-status");

for (String id : referencedIds) {
    Part image = MimeTree.requireContentId(message, id);
    assertThat(image.getDisposition())
            .isEqualToIgnoringCase(Part.INLINE);
}
~~~

The regex above is a test helper **for the application's simple Content-ID convention**, not a general-purpose RFC 2392 parser. CID URLs can contain percent-encoded characters, and HTML can reference images via CSS or other attributes. If templates support complex URIs, use a proper HTML parser and URI decoding instead of claiming this regex covers every case.

### Check the reverse direction

Beyond ensuring every CID in HTML has a matching part, you can verify no inline part was left unused (unless intentional by design):

~~~text
HTML references: {header-logo, order-status}
MIME inline IDs: {header-logo, order-status}

Both sets should match per template policy.
~~~

Checking the reverse direction catches "orphan" parts that bloat email size. Still, not every inline resource must be referenced in every HTML alternative variant; apply the rule according to your application's templates.

## 16. Verify multiple attachments: exact filenames without swapped contents

Example email with two PDFs:

~~~java
helper.setText(
        "Invoice and terms attached.",
        false);

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoiceBytes),
        "application/pdf");
helper.addAttachment(
        "terms.pdf",
        new ByteArrayResource(termsBytes),
        "application/pdf");
~~~

In tests, look them up by filename:

~~~java
Part invoice = MimeTree.requireFilename(
        message, "invoice.pdf");
Part terms = MimeTree.requireFilename(
        message, "terms.pdf");

try (var invoiceStream = invoice.getInputStream();
     var termsStream = terms.getInputStream()) {

    assertThat(invoiceStream.readAllBytes())
            .containsExactly(invoiceBytes);
    assertThat(termsStream.readAllBytes())
            .containsExactly(termsBytes);
}
~~~

If you look up two parts by `application/pdf` and assume the first is invoice and the second is terms, tests become brittle and may miss swapped contents. Filename serves as a sound key when the application guarantees distinct attachment names.

### Should you verify attachment ordering?

MIME part order can affect some clients, yet applications do not always need to guarantee visual file ordering. If business rules mandate attachment order, write an ordering test on a deterministic structure. Otherwise, check the set of filenames and mapped bytes so tests do not fail merely because code changes insertion order.

### Never let filenames become dangerous paths

Displayed filenames should be generated by the application and free of path segments like:

~~~text
../../internal/private.pdf
C:\secrets\key.txt
~~~

In tests for attachments derived from user or external inputs, verify filenames are sanitized and contain no path separators or control characters. This is an **input-security check**, separate from normal MIME assertions.

## 17. Negative tests: when code adds the wrong part type

A strong unit test verifies not only the happy path, but also catches mistakes likely to occur during refactoring:

### Confusing addAttachment with addInline

Suppose a developer changes:

~~~java
helper.addAttachment(
        "invoice.pdf", pdfResource, "application/pdf");
~~~

into:

~~~java
helper.addInline(
        "invoice",
        pdfResource,
        "application/pdf");
~~~

The email may still carry the exact PDF bytes, yet disposition becomes inline and the expected filename disappears. The attachment test in Section 10 catches this because:

~~~java
assertThat(pdf.getDisposition())
        .isEqualToIgnoringCase(Part.ATTACHMENT);
~~~

Thus **comparing bytes alone is not enough**: a part with the right bytes yet the wrong delivery semantics can prevent recipients from downloading the file easily.

### Confusing addInline with addAttachment

~~~java
helper.addAttachment(
        "logo.png",
        logoResource,
        "image/png");
~~~

HTML may still reference `cid:order-logo`, yet the added part lacks the expected Content-ID. `MimeTree.requireContentId(message, "order-logo")` will fail. Filename and MIME type cannot substitute for the Content-ID header.

### Using a helper with multipart disabled

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message, false, "UTF-8");

helper.addAttachment("invoice.pdf", pdfResource);
~~~

With multipart disabled on the helper, adding attachments or inline resources is invalid and can throw an exception. Test that the composer **selects an appropriate multipart mode** whenever business requirements include attachments or CID images.

### Wrong or case-mismatched CID in HTML

~~~html
<img src="cid:order-logo">
~~~

~~~java
helper.addInline("Order-Logo", logoResource, "image/png");
~~~

Never assume every mail client treats both IDs as identical. Use consistent, stable Content-IDs across templates and composers; test exact matching against the application-defined ID.

### Duplicate Content-IDs

~~~java
helper.addInline(
        "logo",
        resourceA,
        "image/png");
helper.addInline(
        "logo",
        resourceB,
        "image/jpeg");
~~~

The message ends up with two body parts sharing the same ID. Tests must enforce ID uniqueness per policy instead of merely asserting one of the two parts exists.

### Missing attachment while still calling the sender

If the business rule requires sending an invoice yet the repository returns null/empty bytes, the service might send a notice email missing the invoice. A test should verify **business validation**:

~~~java
assertThatThrownBy(() ->
        service.sendInvoice(
                "customer@example.test",
                validLogo,
                null))
        .isInstanceOf(IllegalArgumentException.class);
~~~

This assertion holds only if the service is designed to **reject null before calling the sender**. The exact exception type depends on the application's contract; never expect Jakarta Mail to replace input validation automatically.

## 18. Verify binary data after Content-Transfer-Encoding

An attachment is not transmitted over raw SMTP as raw original bytes; MIME typically encodes binary payloads using Base64:

~~~mime
Content-Type: application/pdf; name="invoice.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"

JVBERi0xLjQK...
~~~

An inline image may similarly have:

~~~mime
Content-Type: image/png
Content-ID: <order-logo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

iVBORw0KGgo...
~~~

To check bytes:

~~~java
try (var stream = part.getInputStream()) {
    byte[] actual = stream.readAllBytes();
    assertThat(actual).containsExactly(expectedBytes);
}
~~~

Never compare raw Base64 strings inside the message against hand-encoded strings, because line wrapping and implementation details can vary. Decoded bytes represent the actual data the application intends to deliver.

### Do not necessarily assert a fixed Content-Transfer-Encoding value

Depending on MIME type, content, library, and transport, text parts may use quoted-printable, Base64, or another encoding. For binary parts, Base64 is very common, yet tests should lock down `Content-Transfer-Encoding` only when business or compatibility rules truly require it.

Assertions to prioritize:

1. Decoded bytes match source bytes.
2. Content-Type is declared properly.
3. Disposition is appropriate.
4. CID or filename matches expectations.

Avoid coupling tests to unnecessary implementation details.

### Test byte arrays need not be valid files

For assembly unit tests, data such as:

~~~java
byte[] fakePng = new byte[] {1, 2, 3};
~~~

suffices to test that bytes are not altered. However, if you want to confirm recipients can open the PNG file, use a valid image fixture; file validity cannot be inferred from MIME headers.

## 19. Test with ClassPathResource and real fixture files

When checking that attachment/resource bytes match files shipped with the application, use `ClassPathResource`:

~~~java
import org.springframework.core.io.ClassPathResource;

helper.setText(html, true);
helper.addInline(
        "company-logo",
        new ClassPathResource("mail-test/logo.png"),
        "image/png");

helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail-test/invoice.pdf"),
        "application/pdf");
~~~

Suppose the project has:

~~~text
src/test/resources/
└── mail-test/
    ├── logo.png
    └── invoice.pdf
~~~

Tests can compare bytes:

~~~java
ClassPathResource expectedPdf =
        new ClassPathResource("mail-test/invoice.pdf");

byte[] original;
try (var input = expectedPdf.getInputStream()) {
    original = input.readAllBytes();
}

Part attached = MimeTree.requireFilename(
        parsedMessage, "invoice.pdf");

try (var input = attached.getInputStream()) {
    assertThat(input.readAllBytes())
            .containsExactly(original);
}
~~~

`ClassPathResource` fits small, immutable fixtures. In production, streaming from object storage or the filesystem may be needed, while re-readability strategies and size limits still apply.

### Check for missing resources

If `mail-test/logo.png` does not exist:

- `ClassPathResource` can still be instantiated.
- Errors surface only when opening the input stream or serializing/sending the message.

Therefore, a test that only calls `new ClassPathResource(...)` does not prove the resource exists. Assert `exists()` or force the message to read the resource via a round-trip:

~~~java
ClassPathResource logo =
        new ClassPathResource("mail-test/logo.png");

assertThat(logo.exists()).isTrue();
~~~

If the composer must report a clear error when a resource is missing, test the exception at **the exact stage** where the file is actually read, without assuming every `addInline` overload eagerly loads bytes when invoked.

### Never depend on absolute paths of CI runners

Paths like `C:\Users\developer\Desktop\invoice.pdf` or `/tmp/invoice.pdf` easily make tests run on only one machine. Keep fixtures on the classpath or create them in a temporary directory via JUnit `@TempDir` with test-controlled bytes.

## 20. Single-read resources: risks of InputStreamResource

Some attachment sources only provide a single open stream. If the stream is consumed while building the message, a subsequent serialization or resend may have no data left:

~~~text
Single-use InputStream
      |
      v
Mail composer reads
      |
      v
InputStream hits EOF or closes
      |
      v
Jakarta Mail serializes again
      |
      v
Empty attachment or IOException
~~~

`InputStreamResource` usually wraps one specific `InputStream`, not a factory creating fresh streams. With Spring Mail, attachment sources should be able to supply a new `InputStream` when needed (especially when the library checks size, encodes, or serializes). `ByteArrayResource` and `ClassPathResource` are usually better choices in examples/tests.

For large files, avoid loading everything into a byte array if heap pressure is a concern. Design an `InputStreamSource` that opens a fresh stream from a file/object store on each read, while ensuring:

- Resource access permissions remain valid throughout mail creation/sending.
- Source data does not mutate between reads.
- Data carries a checksum or version identifier if needed.
- Proper timeouts, size caps, and I/O error handling are in place.

### Tests that catch non-re-readable resources

One approach:

1. Build the message from the resource.
2. Serialize once.
3. Re-parse and verify bytes.
4. If business rules require resending/copying the message, serialize again from the same source or rebuild a fresh message.
5. Verify the resource can still open the required stream.

Do not try to force every single-use resource into a reusable one without understanding the adapter. When an application sends asynchronously via a queue or outbox minutes later, store a **durable resource reference** or protected snapshot rather than holding an open HTTP-request `InputStream` until a worker runs.

## 21. Test plain text and HTML content alongside resources

Attachments and inline resources usually accompany HTML emails. Unit tests should verify that plain-text and HTML versions carry matching key content, not just that the parts exist:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;

class AlternativeBodyTest {
    @Test
    void containsReadableTextAndHtml() throws Exception {
        MimeMessage message = TestMailFactory.message();

        Part plainPart =
                MimeTree.requireMimeType(message, "text/plain");
        Part htmlPart =
                MimeTree.requireMimeType(message, "text/html");

        String plain = (String) plainPart.getContent();
        String html = (String) htmlPart.getContent();

        assertThat(plain).contains("ORD-001");
        assertThat(html).contains("ORD-001");
        assertThat(html).contains("cid:order-logo");

        assertThat(plainPart.getContentType())
                .containsIgnoringCase("charset=UTF-8");
        assertThat(htmlPart.getContentType())
                .containsIgnoringCase("charset=UTF-8");
    }
}
~~~

This checks key content/facts rather than snapshotting the entire HTML. When both text and HTML bodies contain the order number, tests depend little on whitespace, CSS, or attribute ordering.

### When should HTML escaping be tested?

If customer names come from external data:

~~~text
Name: <script>alert(1)</script>
~~~

HTML templates must escape data appropriately to prevent injecting arbitrary HTML/JavaScript into messages. This tests **template rendering and input safety**, which deserves dedicated tests with special payloads. Do not confuse it with verifying Content-ID or MIME attachments.

Likewise, UTF-8 charset preserves Vietnamese characters, yet does not replace HTML escaping or turn arbitrary text into safe HTML.

## 22. Unreliable assertions to avoid

### Only verifying the send method

~~~java
verify(sender).send(any(MimeMessage.class));
~~~

This test passes even when the PDF is missing or the CID is wrong. Capture the message and inspect its structure/bytes.

### Comparing raw Content-Type with exact string equality

~~~java
assertThat(part.getContentType())
        .isEqualTo("application/pdf");
~~~

Headers may include parameters such as `name="invoice.pdf"` or charset. Use:

~~~java
assertThat(part.isMimeType("application/pdf")).isTrue();
~~~

to check the primary media type as supported by Jakarta Mail.

### Comparing only the raw filename header

~~~java
assertThat(part.getHeader("Content-Disposition")[0])
        .isEqualTo("attachment; filename=invoice.pdf");
~~~

Headers may differ in quoting, folding, or encoding. Test instead:

~~~java
assertThat(part.getDisposition())
        .isEqualToIgnoringCase(Part.ATTACHMENT);
assertThat(part.getFileName())
        .isEqualTo("invoice.pdf");
~~~

### Assuming part ordering is immutable

~~~java
Multipart multipart = (Multipart) message.getContent();
Part image = multipart.getBodyPart(1);
~~~

With mixed-related, part index 1 of the root may be the PDF, not the image. When testing structure, walk the exact nesting level; when simply finding content, use a recursive helper.

### Relying on `Part.getSize()` to compare bytes

`Part.getSize()` can return raw/encoded size or an unknown value (such as `-1`) depending on implementation. To compare binary payloads, read `getInputStream()` and compare decoded bytes. For large files, stream and compare checksums instead of loading everything onto the heap.

### Snapshotting the entire email source

MIME boundaries, header folding, `Message-ID`, `Date`, and encoding can change without breaking functionality. Do not turn implementation details into test contracts when the goal is verifying attachments/CIDs.

### Claiming a client renders properly from a unit test

Even when raw MIME is valid, mail clients may block images, lack HTML/CSS support, or list inline parts in the attachment list. Unit tests are the foundation; visual rendering must be verified separately on target clients.

## 23. Bugs and symptom-based diagnostics

| Symptom | Check in unit tests | Resolution |
|---|---|---|
| Logo shows as an attachment | Image disposition, related nesting | Use `addInline` and appropriate mixed-related mode |
| Logo missing in body | HTML `cid:...` and part Content-ID | Synchronize ID between template and `addInline` |
| Logo disappears when PDF is added | Related and mixed group placement | Use a mode supporting nested related + mixed |
| PDF does not appear | `requireFilename`, attachment disposition | Check `addAttachment` and branch logic |
| PDF downloads yet is empty | Bytes after `getInputStream` | Check resource and stream re-readability |
| PDF differs from source file | Byte checksum/decoded comparison | Check snapshot/resource version |
| Two images swapped | Content-ID and bytes of each part | Test by ID instead of first MIME type match |
| Both text/plain and text/html show simultaneously | Alternative structure | Use `setText(plain, html)` |
| Only plain text appears | HTML part and alternative | Check MIME test, then client behavior |
| Vietnamese filename corrupted | `getFileName()` after round-trip | Check Jakarta Mail filename encoding and client |
| Test passes yet email client still fails | Raw MIME at receiver side | Use SMTP sink/client test, inspect gateway rewriting |
| AddInline fails at runtime | Multipart flag/mode and resource | Initialize helper with appropriate multipart mode |
| Mock test misses attachment | Preparator callback was never run | Use Mockito Answer or capture the right API |
| Error appears only during real send | Resource I/O, SMTP transport, provider | Run round-trip and SMTP integration tests |

### Distinguish three different failure categories

~~~text
1. Composition error:
   - wrong part added, unreadable resource,
     incorrect constructor/helper usage

2. SMTP submission error:
   - authentication failure, connection timeout,
     provider rejects recipient/quota

3. Client rendering error:
   - images blocked, unsupported HTML/CSS,
     varying inline attachment handling
~~~

A strong MIME unit test catches layer 1. It does not automatically handle issues in layers 2 and 3.

## 24. When are SMTP sinks and rendering tests needed?

After unit tests pass, add integration tests when email client compatibility is critical:

~~~text
OrderMailService
      |
      v
JavaMailSender
      |
      v
SMTP sink / local mail server
      |
      +-- Raw RFC 822/MIME source
      +-- MIME parts and attachments
      +-- SMTP acceptance
      |
      v
Then: test mailbox on real clients
~~~

An SMTP sink like Mailpit or GreenMail verifies messages are actually sent over SMTP without reaching real customers. Depending on the tool, you can inspect raw source, headers, body parts, and attachments.

For client rendering requirements, use managed test accounts and verify:

- The logo renders properly in Gmail web/mobile and other target clients.
- The PDF can be downloaded/opened.
- Filenames display cleanly.
- Content remains readable if the client blocks images.
- HTML and plain text do not appear simultaneously as two separate bodies.

SMTP acceptance does not guarantee inbox delivery. DKIM, antispam, mailbox filtering, quotas, and client policies still govern delivery and rendering.

### Never use production SMTP for unit tests

Unit tests must never depend on:

- Production SMTP credentials.
- External DNS/networks.
- Real recipients.
- Provider quotas or deliverability.

If a Content-ID test needs internet access to run, it is testing too many layers at once. Separate unit, integration, and end-to-end tests so failures pinpoint exact causes.

## 25. Security when testing attachments and inline resources

Emails can carry personal documents, invoices, QR images, sensitive links, or internal files. MIME tests must pay attention to both **resource access control** and **data leaks via test artifacts**.

### Never use real customer data as fixtures

Files in `src/test/resources` may be committed, packaged into test artifacts, cached in CI, or uploaded to reporting tools. Use:

- Self-generated PDFs/PNGs containing dummy data.
- `@example.test` addresses or domains reserved for testing.
- No OTPs, access tokens, account numbers, or PII.
- Files small enough to test cleanly in CI.

### Avoid logging attachment bytes on test failure

When an assertion fails, frameworks can print actual/expected values. With large byte arrays, output becomes huge; with real data, sensitive info can leak.

For small fixtures, `containsExactly` works well. For large files, compare hashes instead:

~~~java
import java.security.MessageDigest;
import java.util.Arrays;

byte[] expectedDigest =
        MessageDigest.getInstance("SHA-256").digest(expectedBytes);
byte[] actualDigest =
        MessageDigest.getInstance("SHA-256").digest(actualBytes);

assertThat(actualDigest).containsExactly(expectedDigest);
~~~

The test compares hashes so failure output does not dump full binary payloads. For truly large files, compute digests via streams instead of loading both files into byte arrays.

### Never take attachment paths directly from user input

If an application allows:

~~~java
helper.addAttachment(
        request.fileName(),
        new FileSystemResource(request.path()));
~~~

with an unvalidated `request.path()`, attackers could trick the backend into attaching files it has permission to read, causing data exfiltration. Business tests must verify only resources owned by the authorized user/tenant can be attached.

Testing `Content-Disposition` alone **does not prove the file was authorized for sending**. Authorization must be enforced before building MIME.

### MIME type and extension are not file-validation mechanisms

`image/png` or `application/pdf` are merely labels. If attachment sources are untrusted, you may need magic-byte checks, real format validation, size caps, malware scanning policies, and allowed-file-type enforcement.

Those tests belong to the resource ingestion/validation layer and do not replace MIME assembly tests.

## 26. Performance and memory limits of MIME unit tests

The examples use `ByteArrayResource` and `readAllBytes()` because payloads are small, clear, and easy to assert. Do not copy this pattern verbatim for attachments weighing hundreds of MB:

- Byte arrays hold the entire file on the heap.
- Serializing into `ByteArrayOutputStream` can allocate an extra raw MIME copy.
- Re-parsing can retain additional metadata, content caches, or processing streams.
- Comparing multiple copies in one test can trigger OOM or slow down CI.

A tiered strategy:

| Test scale | Data | Verification approach |
|---|---|---|
| MIME unit | A few bytes to a few KB | ByteArrayResource, full decoded-byte comparison |
| Resource test | Small valid fixture files | ClassPathResource, checksum/byte check |
| Large-file integration | Large files within realistic limits | Streaming, checksums, heap/timeout controls |
| SMTP end-to-end | Sizes matching provider policy | SMTP sink/test accounts, measuring size/latency and errors |

### MIME size is typically larger than the original file

A Base64-encoded file grows by roughly one-third before adding line breaks and MIME headers. With multiple attachments, calculate against the SMTP provider's total message size limit, not merely the sum of raw file bytes.

Size-limit tests should verify application policy before sending; there is no need to cram a huge attachment into a unit test just to "guess" whether the provider accepts it.

### Never rely on absolute unit-test latency

An assertion like "MIME must build within 20 ms" can flake on slow CI runners or cold JVMs. When benchmarking performance, measure separately with proper tools while controlling source size, part count, memory, and execution environment.

## 27. Recommended test scenario matrix

A valuable test suite should cover structure, data, and common mistakes:

| ID | Scenario | Key assertion |
|---|---|---|
| TC-01 | HTML-only email | Has `text/html`, no unintended attachments |
| TC-02 | Plain + HTML | Has `multipart/alternative` and both accurate bodies |
| TC-03 | Single inline image | `image/png`, `inline`, Content-ID matches HTML |
| TC-04 | Two images of same MIME type | Two distinct Content-IDs, right bytes for each |
| TC-05 | Single PDF attachment | Right filename, `attachment`, MIME type, and bytes |
| TC-06 | Two differently named PDFs | Each filename maps to the right bytes |
| TC-07 | HTML + inline image + PDF | Related group for image, mixed for PDF |
| TC-08 | Wrong CID in HTML | Reference vs Content-ID check catches missing part |
| TC-09 | Two inline parts sharing CID | Uniqueness test flags error |
| TC-10 | Calling `addInline` as attachment | Disposition/CID assertion fails |
| TC-11 | Calling `addAttachment` as inline | Filename/disposition assertion fails |
| TC-12 | Missing classpath resource | Composer/serialization reports clear error |
| TC-13 | Single-use InputStreamResource | Re-read/serialization test exposes lifecycle issue |
| TC-14 | Unicode subject and filename | Decoded values stay intact after MIME round-trip |
| TC-15 | Encoded binary content | `getInputStream` returns exact decoded bytes |
| TC-16 | Service uses `send(MimeMessage)` | ArgumentCaptor captures right message |
| TC-17 | Service uses `send(MimeMessagePreparator)` | Mockito Answer executes callback and checks MIME |
| TC-18 | Unauthorized attachment | Service rejects before sending |
| TC-19 | Oversized file | Application validation rejects, no SMTP submission |
| TC-20 | Post-relay email | Integration test checks raw MIME at receiving server |

Not every project needs 20 separate tests. You can group assertions sharing one fixture into a readable test as long as failures pinpoint what broke. Avoid cramming every email type into one giant test that obscures root causes.

### Tests must be independent of execution order

Each test should construct a fresh `MimeMessage` and its own resources; never share a mutable `MimeMessage` across parallel tests. MIME structure, headers, and body parts can be mutated during composition/serialization; sharing objects causes race conditions and flaky tests.

### Do not share uncontrolled mutable byte arrays

`ByteArrayResource` may keep a reference to the passed byte array. If other code mutates those bytes after constructing the resource, serialized content may change later. For async workflows, supply immutable snapshots or copy bytes as needed to avoid timing-dependent state.

## 28. Diagnostic workflow when a MIME test fails

~~~mermaid
flowchart TD
    A[Attachment/CID unit test fails] --> B{Can message serialize?}
    B -- No --> C[Check resource, DataHandler, multipart mode]
    B -- Yes --> D{Right multipart tree?}
    D -- No --> E[Check mode + setText/addInline order]
    D -- Yes --> F{Content-ID matches HTML?}
    F -- No --> G[Sync template and ID]
    F -- Yes --> H{Right disposition and filename?}
    H -- No --> I[Check addInline vs addAttachment]
    H -- Yes --> J{Decoded bytes match source?}
    J -- No --> K[Check stream/readback/encoding]
    J -- Yes --> L[Move to SMTP/client integration if issue appears only in Inbox]
~~~

Detailed diagnostic steps:

1. Check whether code calls `setText(...)` before `addInline(...)`.
2. Check which multipart mode the `MimeMessageHelper` constructor uses.
3. Inspect the root subtype and related/alternative/mixed groups.
4. Check HTML `cid:...` references.
5. Locate the part with the matching Content-ID, checking subtype and disposition.
6. Inspect attachment filename, media type, and disposition.
7. Re-parse raw MIME and compare decoded bytes against source.
8. If the message is right in unit tests yet broken after SMTP, compare raw MIME at the receiving side and check provider/gateway behavior.
9. If received raw MIME is right yet UI breaks, test the target client/version and image-blocking policies.

**Do not change SMTP host, port, username, or password just because a unit test cannot find a Content-ID.** That is an application-side MIME structure bug, usually unrelated to SMTP authentication.

## 29. Frequently asked questions

**Do I need an SMTP server to test attachments?** No. You can build a `MimeMessage` in memory, call `MimeMessageHelper.addAttachment(...)`, and walk `Part` entries to check filename, disposition, Content-Type, and data.

**Do I need an SMTP server to test Content-ID?** No. Both the `Content-ID` header and HTML `cid:...` can be verified before sending.

**Is `verify(sender).send(...)` alone enough?** No. It only proves the service called the sender; it does not prove the email has the right attachments or inline resources. Capture the message and inspect MIME.

**Why re-parse after `writeTo(...)`?** Serialization can expose encoding/header/resource bugs that do not surface when reading only the in-memory object. Re-parsing tests the actual MIME bytes the library generates.

**Why not check `Part.getContentType()` with `equals("image/png")`?** Content-Type can carry parameters. `isMimeType("image/png")` checks the media type properly.

**Must Content-ID have angle brackets?** MIME headers typically have `<id>`, while HTML uses `cid:id`. With `MimeMessageHelper.addInline`, pass the ID without `cid:` or brackets.

**Is Content-ID a filename?** No. Content-ID is a MIME reference identifier; filename is the file name presented to the recipient.

**Can an inline part have a filename?** Yes, depending on how the message is built. Do not assume every inline resource must have a null filename; check Content-ID and disposition purposefully.

**Can an attachment have a Content-ID?** Yes, depending on structure. Therefore never assume every part with a Content-ID is inline; inspect Content-Disposition, nesting position, and HTML references.

**Can I use a few dummy bytes to test images?** Yes, when testing only MIME assembly and byte preservation. Those bytes do not prove a valid PNG/PDF that can be opened or rendered.

**Why not read raw Base64 bytes and compare?** MIME transfer encoding can vary. `Part.getInputStream()` returns decoded bytes to compare against the source.

**How should `MimeMessagePreparator` errors be tested?** When mocking the sender, execute the preparator callback on a real `MimeMessage` using Mockito Answer; merely verifying the callback was passed is not enough.

**Will inline images always render in Gmail/Outlook if tests pass?** No. Email clients also enforce image-blocking policies, HTML/CSS rendering differences, and varying multipart support. Client tests are needed to confirm UI rendering.

**Should large attachments be tested with `ByteArrayResource`?** Only for small fixtures. For large files, test streaming, size limits, checksums, and resources in a separate integration test layer.

**Should `InputStreamResource` be used for inline images?** Be careful if the resource wraps a single-read stream. Prefer sources that can open a fresh stream whenever Jakarta Mail needs to re-read.

**Does every HTML email need multipart?** No. A simple `text/html` body with no inline resources or attachments may not need multipart. Multipart is needed when combining multiple parts/attachments or alternative representations.

## 30. Principles to remember

In **Spring Framework Mail**, testing attachments, inline resources, and Content-ID should focus on **the actual constructed MIME message**, never stopping at verifying `JavaMailSender.send(...)` was called.

Three core principles:

1. **Verify the exact part:** attachments by filename, inline images by Content-ID, media type, and disposition; avoid fixed indices with nested MIME.
2. **Verify the exact relationships:** HTML must reference existing CIDs; inline resources belong to the related group; standalone attachments belong to the mixed group when using the matching mode.
3. **Verify data is unaltered:** serialize/re-parse the message and compare decoded bytes against the original fixture instead of arbitrary Base64/raw MIME snapshots.

A practical testing strategy:

~~~text
Mail composer/service
        |
        v
MimeMessage + MimeMessageHelper
        |
        v
JUnit/Mockito:
   - MIME tree
   - Content-ID ↔ cid: reference
   - Content-Disposition
   - MIME type + filename
   - decoded bytes
        |
        v
MIME round-trip (no SMTP)
        |
        v
SMTP integration when needed
        |
        v
Client rendering test for target Gmail/Outlook
~~~

**A successfully sent email does not guarantee its content displays properly.** MIME unit tests catch composition bugs early, pinpoint the broken part, and reduce troubleshooting from real mailboxes. Combined with SMTP and email-client tests at the right layers, applications gain far stronger control over attachments, embedded images, and Content-ID references.
