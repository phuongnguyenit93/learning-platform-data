# Multipart Order Affects Displayability

## 1. Why Does Multipart Structure Determine How an Email Is Displayed?

In **Spring Framework Mail**, an email can contain multiple content types at the same time: plain text, HTML, images embedded in HTML, and attached files. These parts are packaged in a **MIME multipart** structure. How the parts are organized not only affects message size, but also determines how email clients identify the main content, which images belong to HTML, and which files the recipient should download.

An email can be sent successfully over SMTP and still render incorrectly:

- A logo image shows up as an attachment instead of appearing inside the HTML.
- HTML is displayed, yet CID images fail to appear.
- Users see both the text version and the HTML version as two independent blocks of content.
- A PDF file is treated as part of related content instead of an attachment.
- The email displays properly in one client but breaks in another.

These situations usually relate to **Content-Type**, **multipart nesting**, **Content-ID**, **Content-Disposition**, and the order in which parts are constructed.

A multi-format email typically has these components:

| Component | MIME type / attributes | Role |
|---|---|---|
| Plain text | `text/plain` | Text version for clients that do not render HTML |
| HTML | `text/html` | Formatted version with layout and CID image references |
| Inline image | `image/png`, `image/jpeg`... and `Content-ID` | Resource referenced by HTML |
| Attachment | `application/pdf`, `application/octet-stream`... | File for the recipient to download |

**Multipart is not simply a list of files.** Multipart types express relationships between parts:

- `multipart/alternative`: multiple alternative representations of the same content.
- `multipart/related`: a root resource (usually HTML) together with the resources it references.
- `multipart/mixed`: a set of independent parts sent together, typically the message body and attachments.

Choosing the appropriate structure helps email clients interpret the purpose of each part accurately.

## 2. MIME multipart/alternative: Text and HTML Are Two Alternative Versions

When an email has both text/plain and text/html, these two parts usually belong to **multipart/alternative**. They express the same message in two different formats, not two independent notifications.

~~~text
multipart/alternative
  |
  +-- text/plain; charset=UTF-8
  |
  +-- text/html; charset=UTF-8
~~~

Example:

~~~java
String plainText = """
        Hello!
        Order ORD-001 has been confirmed.
        Thank you for using our service.
        """;

String htmlText = """
        <html lang="en">
          <body>
            <h1>Hello!</h1>
            <p>Order <strong>ORD-001</strong>
               has been confirmed.</p>
            <p>Thank you for using our service.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);
~~~

With the two-parameter overload, `MimeMessageHelper.setText(plainText, htmlText)` creates two alternative contents. Email clients typically choose the richest form they support, usually HTML; text-only clients can pick plain text.

**The order of parts in multipart/alternative matters.** By MIME convention, alternatives are ordered from the least rich form to the richest form. Clients may choose the last part they understand. Thus, when manually building multipart/alternative with Jakarta Mail, text/plain is normally placed before text/html.

With `MimeMessageHelper`, use the `setText(plainText, htmlText)` overload instead of creating body parts manually unless there is a special need. The helper manages the order and charset of the alternatives.

### When Is multipart/alternative Not Needed?

If an email has only simple text content, `SimpleMailMessage` or a `MimeMessage` with `text/plain` is sufficient. If an email has only HTML and needs no text version, you can call `setText(html, true)`. You do not need to create multipart/alternative solely to use HTML.

However, emails with important HTML should usually have a corresponding text version to improve readability on clients and systems that process only plain text.

## 3. MIME multipart/related: HTML and the Resources It References

An HTML body can reference images using CID:

~~~html
<img src="cid:brand-logo" alt="Company logo">
~~~

The image is added to the message as a MIME part with a matching `Content-ID`. **multipart/related** expresses that these parts are related to each other: one part is the root content, and other parts are resources needed to display that content.

~~~text
multipart/related
  |
  +-- text/html
  |     |
  |     +-- <img src="cid:brand-logo">
  |
  +-- image/png
        Content-ID: <brand-logo>
        Content-Disposition: inline
~~~

In this structure, HTML is the main content; the PNG image is a related resource. The email client resolves `cid:brand-logo` by looking up the body part with the matching Content-ID.

In Spring:

~~~java
helper.setText(html, true);
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/brand-logo.png"),
        "image/png");
~~~

`addInline` must be called **after `setText`**. Once the body has been set, the helper attaches the resource into the right multipart structure. Calling them in the reverse order may prevent some mail readers from resolving the CID properly.

### CID and Content-ID Must Match

In HTML:

~~~html
<img src="cid:brand-logo" alt="Company">
~~~

In Java:

~~~java
helper.addInline("brand-logo", logoResource, "image/png");
~~~

Do not add the `cid:` prefix to the `contentId` argument of `addInline`. The helper generates the Content-ID header for the MIME part. If HTML uses `cid:brand-logo` while the code passes ID `logo`, the email may still be accepted by SMTP, yet the image will not appear.

## 4. MIME multipart/mixed: Message Body and Independent Parts

**multipart/mixed** is commonly used to send a message body along with attachments. The parts are independent components packaged in the same message.

~~~text
multipart/mixed
  |
  +-- text/plain or text/html
  |
  +-- application/pdf
        Content-Disposition: attachment
        filename="invoice.pdf"
~~~

Example adding an attachment:

~~~java
helper.setText("Your invoice is attached.", false);
helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/files/invoice.pdf"));
~~~

An attachment is neither an alternative of the body nor a resource HTML needs for rendering. It is an independent part that email clients can present in the attachments area.

If an email has HTML, inline images, and a PDF, using only a flat multipart/mixed can cause parts to be interpreted unexpectedly in some clients. In that case, a nested structure is needed to accurately express the relationship between HTML and images while keeping the PDF as an independent attachment.

## 5. Why Is Nested Multipart Needed for HTML, Inline Images, and Attachments?

An email often has all three requirements:

1. Plain text for clients that do not render HTML.
2. HTML and CID images to create rich content.
3. A PDF attachment for the recipient to download.

An appropriate conceptual MIME structure can be:

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
        filename="invoice.pdf"
~~~

Relationships in this structure:

- **Alternative** places plain and HTML as two versions of the same content.
- **Related** links the image with the HTML referencing the CID.
- **Mixed** places the message body and the PDF attachment side by side as independent parts.

This is a common MIME model for HTML emails with inline images and attachments. The actual nesting structure may vary depending on multipart mode and how the library constructs the message, but the meaning of the relationships must be preserved.

If an image part is placed as an unrelated peer attachment to HTML, clients may display it as a loose file or fail to find the CID. If a PDF is placed inside multipart/related alongside HTML, clients may treat it as a content resource rather than a regular attachment.

## 6. Multipart Modes of MimeMessageHelper

Spring provides multipart modes in `MimeMessageHelper`. When creating the helper, the chosen mode affects how the helper organizes MIME parts:

| Mode | Conceptual structure | Usage |
|---|---|---|
| `MULTIPART_MODE_NO` | No multipart created | Simple single-part email, no inline/attachments |
| `MULTIPART_MODE_MIXED` | A multipart/mixed at root | Content and added parts at the same level |
| `MULTIPART_MODE_RELATED` | A multipart/related at root | HTML and inline resources, usually no independent attachments |
| `MULTIPART_MODE_MIXED_RELATED` | multipart/mixed root, nested multipart/related | HTML, inline resources, and attachments in the same message |

When an HTML email needs both inline images and attachments, `MULTIPART_MODE_MIXED_RELATED` is normally the right choice. It is also the **default mode of the boolean multipart constructor** in common Spring Framework versions:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

You can specify the mode explicitly so readers see the intent:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name());
~~~

### MULTIPART_MODE_RELATED

This mode creates multipart/related at the root. It fits HTML emails with inline images that do not need an independent attachment group. If an attachment is added into the same related structure, some clients may behave unexpectedly because the attachment and inline resources sit at the same level.

### MULTIPART_MODE_MIXED

This mode creates multipart/mixed at the root and adds parts at the same level. A flat structure may work in some clients, yet the relationship between HTML and inline resources is not expressed via an explicit nested related group. Compatibility may therefore be worse for complex HTML emails.

### MULTIPART_MODE_MIXED_RELATED

This mode creates multipart/mixed at the root with a nested multipart/related inside. HTML-related parts, including inline resources, reside in the related area; independent attachments sit at the mixed level. This is usually the right choice when an email has **HTML + CID images + attachments**.

**Do not choose a mode based solely on how many files the email has.** Choose based on the relationships between parts and the rendering requirements of target email clients.
## 7. Method Call Order on MimeMessageHelper

When a message has multiple formats, set the main content before adding resources referenced by that content. An easy-to-follow practical sequence:

1. Create `MimeMessage`.
2. Create `MimeMessageHelper` with the appropriate multipart mode.
3. Set From, To, Cc/Bcc, Subject, and necessary headers.
4. Call `setText(...)` to create the plain text body, HTML body, or both.
5. Call `addInline(...)` for images referenced by HTML via CID.
6. Call `addAttachment(...)` for independent files the recipient downloads.
7. Send the message using `JavaMailSender.send(...)`.

Diagram:

~~~text
createMimeMessage()
        |
        v
new MimeMessageHelper(..., multipartMode, "UTF-8")
        |
        v
setFrom / setTo / setSubject
        |
        v
setText(plainText, htmlText)
        |
        v
addInline(cid, resource)
        |
        v
addAttachment(filename, resource)
        |
        v
JavaMailSender.send(message)
~~~

The most important ordering condition for inline images is that **setText must precede addInline**. Attachments should be added after the main content and inline resources are set so the code flow clearly mirrors the message structure. There is no need to call setText again after adding images.

### Why Not Call setText Again at the End?

setText sets the message body part. Calling it again after inline resources have been added may replace or alter the body/multipart part to which the resources are linked. Prepare complete content first, call setText once, and then attach the corresponding resources.

If content must be changed after creating the helper, the safer and clearer approach is usually rebuilding the message/helper from scratch in the right order, rather than patching individual MIME tree parts in a completed state.

## 8. Complete Example: Text, HTML, Inline Image, and PDF Attachment

The example below uses `MULTIPART_MODE_MIXED_RELATED` to express each part's purpose clearly:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
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

    public void sendOrderConfirmation(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        String plainText = """
                Hello!
                Order ORD-2026-001 has been confirmed.
                The PDF invoice is attached to this email.
                """;

        String htmlText = """
                <!doctype html>
                <html lang="en">
                  <head><meta charset="UTF-8"></head>
                  <body>
                    <img src="cid:company-logo"
                         alt="Company"
                         width="140">
                    <h1>Order Confirmed</h1>
                    <p>Order code: <strong>ORD-2026-001</strong></p>
                    <p>The PDF invoice is attached to this email.</p>
                  </body>
                </html>
                """;

        helper.setFrom("orders@example.com");
        helper.setTo(recipient);
        helper.setSubject("Order Confirmation ORD-2026-001");

        // Set the two alternatives: text/plain and text/html.
        helper.setText(plainText, htmlText);

        // Logo image belongs to HTML content: add after setText.
        helper.addInline(
                "company-logo",
                new ClassPathResource("mail/images/company-logo.png"),
                "image/png");

        // PDF is an independent file for the recipient to download.
        helper.addAttachment(
                "invoice-ORD-2026-001.pdf",
                new ClassPathResource("mail/files/invoice-ORD-2026-001.pdf"),
                "application/pdf");

        mailSender.send(message);
    }
}
~~~

Suppose the resources are located under:

~~~text
src/main/resources/
└── mail/
    ├── images/
    │   └── company-logo.png
    └── files/
        └── invoice-ORD-2026-001.pdf
~~~

In this example:

- setText(plainText, htmlText) creates the alternative part.
- addInline("company-logo", ...) adds the image referenced by HTML.
- addAttachment(...) adds the independent PDF.
- Mixed-related mode groups HTML and the image in related, while keeping the PDF in the outer mixed area.
- UTF-8 charset preserves Vietnamese content accurately.

Do not simply change the multipart mode while leaving everything else unchanged and conclude the email is more compatible. Inspect the serialized message and test with the email clients your application supports.

## 9. Choosing the Multipart Mode by Email Type

A practical guide to choosing a mode:

| Email content | Typically suitable mode | Notes |
|---|---|---|
| Simple plain text | `MULTIPART_MODE_NO` | No inline images or attachments |
| Simple HTML, no images/attachments | No multipart needed or `NO` | Only a single text/html part |
| HTML + inline images, no attachments | `MULTIPART_MODE_RELATED` or default mixed-related | Related expresses images linked to HTML |
| Plain + HTML, no images/attachments | Multipart alternative managed by helper | Use `setText(plain, html)` |
| HTML + inline images + PDF attachment | `MULTIPART_MODE_MIXED_RELATED` | Related inside mixed |
| Plain + HTML + inline images + attachment | `MULTIPART_MODE_MIXED_RELATED` | Common complete structure |
| Multiple part types with custom MIME rules | Custom Jakarta Mail structure | Use only when helper cannot satisfy requirements |

### When There Is Only HTML and an Inline Image

`MULTIPART_MODE_RELATED` can be suitable because the entire message content is one related group: HTML and CID images. `MULTIPART_MODE_MIXED_RELATED` also works, though it adds an extra mixed layer at the root even without independent attachments.

### When There Is an Independent Attachment

If a PDF or document must appear in the attachments area, `MULTIPART_MODE_MIXED_RELATED` expresses the relationship more clearly: the body portion (related group) is one part of the mixed root; the attached file is another independent part.

### When Using Only MULTIPART_MODE_MIXED

Mixed mode places parts at the same root level. A flat structure can be handled by many clients, yet it does not explicitly state that images belong to HTML. Especially when a message has both inline images and attachments, mixed-related is usually a more compatible choice.

## 10. What Happens If the Multipart Mode Is Unsuitable?

Several symptoms may appear:

| Symptom | Potential structural cause |
|---|---|
| CID image becomes a loose attachment | Image part is not in an appropriate related group, CID mismatches, or client handles it differently |
| PDF renders as inline content | Content-Disposition or part placement does not express an attachment properly |
| Only plain text shows despite HTML existing | Client chose the plain text alternative, or alternative structure / Content-Type is wrong |
| Both plain and HTML appear as two sequential blocks | The two parts were not organized as multipart/alternative |
| Image does not display even though CID matches | Part is not in an appropriate related group, wrong Content-ID header, or client blocks/lacks support |
| Attachment disappears after adding inline image | Multipart structure was built wrongly or helper methods were called out of order |
| One client renders differently from another | Clients may apply different heuristics or MIME support levels |

**Not every display issue is caused by multipart mode.** Check CID, Content-Type, Content-Disposition, image data, size, charset, and client image-blocking policies. An email client may deliberately hide images or require the recipient to allow display.

## 11. Content-Disposition and Content-ID Working with Multipart

Two headers commonly govern how clients treat images and attachments:

**Content-ID** identifies a MIME part so other content can reference it. HTML uses a `cid:...` URI and the part carries a matching Content-ID header.

**Content-Disposition** suggests how to present a part:

- `inline`: content may be displayed together with the message.
- `attachment`: content is an independent file for the recipient to download.

Conceptual examples:

~~~mime
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <company-logo>
Content-Disposition: inline
~~~

~~~mime
Content-Type: application/pdf
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"
~~~

**Content-Disposition: inline alone does not guarantee the image appears in the right spot.** HTML must also reference the matching CID, and the MIME hierarchy must express the related relationship. Similarly, having only a Content-ID without an HTML tag referencing it means the image may not be used in the body.

Some email clients may auto-display or group attachments using their own heuristics. Treat MIME headers and multipart hierarchy as the outbound contract, while still verifying the final appearance on target clients.
## 12. Inspecting the MIME Structure Instead of Looking Only at the UI

When an email renders incorrectly, inspect the **serialized message** to see what structure the helper actually generated. Looking only at `addInline` or `addAttachment` calls does not prove the final MIME is correct.

Workflow:

1. Create the message in memory using `MimeMessage` and `MimeMessageHelper`.
2. Call methods in the right order.
3. Call `saveChanges()` to finalize headers and metadata.
4. Serialize with `writeTo(...)`.
5. Parse bytes back into a new `MimeMessage`.
6. Traverse the multipart tree to find parts by MIME type, Content-ID, and Content-Disposition.

Example verifying structure after serialize/parse:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

class MultipartStructureTest {
    @Test
    void buildsAlternativeRelatedAndMixedParts() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("orders@example.test");
        helper.setTo("customer@example.test");
        helper.setSubject("Order confirmation");

        helper.setText(
                "Order ORD-001 is confirmed.",
                "<html><body><img src=\"cid:brand-logo\" "
                        + "alt=\"Brand\">Order ORD-001</body></html>");

        helper.addInline(
                "brand-logo",
                new ByteArrayResource(new byte[] {1, 2, 3, 4}),
                "image/png");
        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(new byte[] {5, 6, 7, 8}),
                "application/pdf");

        message.saveChanges();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        message.writeTo(output);

        MimeMessage parsed = new MimeMessage(
                session,
                new ByteArrayInputStream(output.toByteArray()));

        assertThat(parsed.isMimeType("multipart/mixed")).isTrue();

        List<Part> parts = new ArrayList<>();
        collectParts(parsed, parts);

        assertThat(parts).anySatisfy(part ->
                assertThat(part.isMimeType("multipart/related")).isTrue());
        assertThat(parts).anySatisfy(part ->
                assertThat(part.isMimeType("multipart/alternative")).isTrue());
        assertThat(parts).anySatisfy(part -> {
            assertThat(part.isMimeType("image/png")).isTrue();
            assertThat(part.getDisposition()).isEqualTo(Part.INLINE);
            assertThat(contentId(part)).isEqualTo("brand-logo");
        });
        assertThat(parts).anySatisfy(part -> {
            assertThat(part.isMimeType("application/pdf")).isTrue();
            assertThat(part.getDisposition()).isEqualTo(Part.ATTACHMENT);
        });
    }

    private static void collectParts(
            Part part, List<Part> result) throws Exception {
        result.add(part);
        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                collectParts(child, result);
            }
        }
    }

    private static String contentId(Part part) throws Exception {
        String[] values = part.getHeader("Content-ID");
        if (values == null || values.length == 0) {
            return null;
        }
        return values[0].replace("<", "").replace(">", "").trim();
    }
}
~~~

The example uses short byte arrays to illustrate checking **MIME structure**, not real PNG/PDF files. When testing real rendering capability, use valid fixture files on the classpath and inspect file contents. This test assumes the project's Spring/Jakarta Mail version supports the chosen multipart mode.

### Why Re-Parse the Message?

Reading the same object right after calling helper methods may only reflect in-memory state. Serializing and re-parsing checks the **headers and multiparts actually written to bytes** the way an email client will receive them. This catches bugs occurring while generating boundaries, Content-IDs, Content-Dispositions, or nested structures.

### Do Not Check Parts by Fixed Index

Do not write:

~~~java
Multipart root = (Multipart) parsed.getContent();
BodyPart image = root.getBodyPart(1); // Fragile assumption
~~~

With mixed-related, the image part may sit inside multipart/related nested under root; the PDF part may sit at the mixed level. When adding text alternatives or other resources, indices can shift. Traversing recursively and matching by `isMimeType`, Content-ID, and Content-Disposition is much more resilient.

## 13. Inspecting Raw MIME with an SMTP Sink

Unit tests with Jakarta Mail verify the constructed message. When you need to observe how the message passes through SMTP transport, use a local or CI **SMTP sink/test server**:

~~~text
Application
   |
   | JavaMailSender.send(...)
   v
SMTP sink
   |
   +-- Raw message source
   +-- multipart/mixed root
   +-- multipart/related group
   +-- multipart/alternative group
   +-- Image Content-ID
   +-- Attachment Content-Disposition
~~~

An SMTP sink receives mail without delivering it to real recipients. The sink's UI typically shows raw source and decoded parts, making it easy to compare:

- Subject and headers.
- `Content-Type` of root and child multiparts.
- Whether HTML contains `cid:...`.
- Whether inline images have matching Content-ID and disposition.
- Whether the PDF has filename and attachment disposition.
- Whether text/plain and text/html carry the same meaning.

Do not use real customer mailboxes or sensitive data in an unprotected sink. Capture tools may store full MIME messages and attachments; restrict access and retention time.

### When Should You Send a Test Through Real Email Clients?

A MIME round-trip proves structure and data serialize properly per the library. It does not guarantee all email clients render identically. If the application supports specific versions of Outlook desktop, Outlook web, Gmail, or mobile apps, send a test batch of messages to controlled accounts and observe each client.

An SMTP sink and MIME parser are diagnostic steps; client testing is the step that confirms display experience.
## 14. Email Clients Can Interpret the Same MIME Differently

MIME specifies how a message is represented, yet email clients also have their own logic for rendering content. Some clients handle inline resources, attachments, CSS, and HTML differently. Thus, a valid MIME tree is a necessary condition, though not sufficient by itself to guarantee identical appearance everywhere.

Common differences:

- Clients may select text/plain or text/html based on capabilities and recipient settings.
- Clients may render inline images right inside the body, or list images in the attachments area.
- Clients may hide remote images, whereas CID images are usually resolved from the MIME message; some clients still apply custom policies.
- Clients may strip certain HTML/CSS, lack SVG support, or alter layout.
- Some security systems may scan, rewrite, or strip MIME parts before the message reaches the mailbox.

Therefore, when investigating issues, separate three layers:

1. **Was MIME built properly?** Inspect the raw message and multipart tree.
2. **Did transport/gateways alter the message?** Compare captures before and after the relay if infrastructure allows.
3. **How did the receiving client render it?** Check on supported clients/versions.

Do not conclude Spring Mail built invalid MIME simply because one client fails to show an image. Conversely, an email displaying fine in Gmail does not prove the MIME structure suits every client.

### Client Testing Matrix

A manual test suite can cover:

| Case | What to observe |
|---|---|
| Modern web client | HTML, CID images, attachments, and links |
| Desktop client | Whether inline images appear in the body and PDF appears in attachment list |
| Mobile app | Whether images load/render and layout is readable on small screens |
| Text-only client or plain text mode | Whether the text version has all essential information |
| Image-blocking mode | Whether alt text is meaningful and content does not rely solely on images |
| Mail system with security gateway | Whether MIME parts were renamed, stripped, or rewritten |

Record client versions and test configurations. "Outlook" or "Gmail" can refer to many apps, platforms, and versions; a single test result does not represent all of them absolutely.

## 15. Diagnosing Multipart Issues by Symptom

| Symptom | Check first | Fix |
|---|---|---|
| HTML shows but logo is missing | HTML CID, Content-ID, image part placement | Sync CID; use related group; call setText before addInline |
| Logo appears as an attachment | Content-Disposition and multipart hierarchy | Check addInline and multipart mode |
| PDF missing from attachment list | Content-Disposition, filename, mixed root | Use addAttachment and mixed-related when inline resources exist |
| Both plain text and HTML appear | Was multipart/alternative actually used | Use setText(plain, html), not two independent parts at mixed root |
| Only plain text shows | Which alternative client picked, HTML Content-Type | Inspect MIME parts, alternative structure, and client settings |
| Adding attachment drops inline image | Multipart mode and MIME tree after adding attachment | Use mixed-related, check root/related nesting |
| Image lacks Content-ID | Resource added with addAttachment or wrong CID | Use addInline with exact contentId |
| MIME is right yet client hides image | Client policy, image format, relay/gateway | Try PNG/JPEG, alt text, compare raw MIME across hops |
| File fails to open | File bytes, content type, transfer encoding | Check original resource and declared MIME type |
| Email client reports malformed message | Boundary, nested multipart, headers | Parse raw MIME with Jakarta Mail and check if gateway rewrote it |

### Investigation Workflow

~~~mermaid
flowchart TD
    A[Email renders incorrectly] --> B[Capture raw MIME]
    B --> C{Root multipart matches purpose?}
    C -- No --> D[Re-select multipart mode / structure]
    C -- Yes --> E{Alternative, related, and mixed nested properly?}
    E -- No --> F[Check setText and addInline/addAttachment]
    E -- Yes --> G{CID and disposition correct?}
    G -- No --> H[Fix Content-ID or how part is added]
    G -- Yes --> I{Did relay modify message?}
    I -- Yes --> J[Investigate gateway/security policy]
    I -- No --> K[Inspect email client and rendering support]
~~~

Do not change multipart modes randomly before capturing raw MIME. One tweak might make the email display fine in the client under test while breaking behavior in another client.

## 16. API Ordering Mistakes

### addInline Before setText

This is the most common ordering mistake with HTML and CID:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.addInline("brand-logo", logoResource);
helper.setText(html, true);
~~~

**Do not use this sequence.** When addInline is called first, the helper may not yet have created the body part that the resource needs to link to. Some mail readers may fail to resolve the CID.

Correct sequence:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(html, true);
helper.addInline("brand-logo", logoResource);
~~~

### Calling setText After addInline

If images have already been added and you replace the body with another setText call, the structure may no longer align with the added CIDs. Finalize HTML/plain strings first, call setText once, then add all inline resources.

### Using a Helper Without Multipart Enabled

If you create:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
~~~

then the helper is in non-multipart mode. This configuration cannot be used to add inline resources or attachments as a multipart message. Choose a multipart constructor and the corresponding mode:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

### Calling setText(plain, html) with Swapped Arguments

The two-string overload expects **plainText first, htmlText second**:

~~~java
helper.setText(plainText, htmlText);
~~~

If HTML is passed as the first argument and plain text as the second, the helper misinterprets the roles of both parts. Clients may pick unintended content or display HTML tags as literal text.

## 17. Charset and Transfer Encoding in Each Part

Multipart mode determines relationships between parts, but **does not replace charset configuration**. Each text part still needs an appropriate Content-Type, for example:

~~~mime
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

~~~mime
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

In Spring:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name());
~~~

Passing UTF-8 ensures text parts are built with the right charset. Images and PDFs are binary data, so they have their respective content types and appropriate transfer encoding, typically Base64. Do not apply UTF-8 charset to image or PDF bytes as if they were text.

If text/plain is fine while HTML has garbled characters, inspect each part separately. If both are wrong, check source data and shared encoding configuration. If text is fine while images are missing, the issue is much more likely in CID/multipart/resources rather than charset.
## 18. Testing Across Multipart Configurations

When an application has multiple email types, maintain separate tests for each configuration:

| Test case | Content | What to verify |
|---|---|---|
| Plain only | Single text/plain body | No unnecessary multipart created |
| HTML only | Single text/html body | Content-Type and charset are right |
| Plain + HTML | Two alternatives | Same information, right alternative order |
| HTML + inline image | Related group | CID matches image part |
| HTML + attachment | Content and independent file | Attachment has matching filename/disposition |
| Plain + HTML + inline image + attachment | Nested mixed/related/alternative | Root, nested groups, and each part are right |

Not every combination needs an SMTP integration test. Most structures can be verified by creating a MimeMessage in memory, serializing it, and parsing it back. Use an SMTP sink only when verifying transport or how a provider receives the message.

### Checking alternative

For a message with only text/plain and text/html, re-parse and verify the message has multipart/alternative or an equivalent alternative structure built by the helper. Traverse parts and confirm:

- A text/plain part exists.
- A text/html part exists.
- Both parts describe the same message.
- Each part's charset is declared properly.

Do not assert the entire HTML with one long snapshot if the goal is merely checking content. Verify key information and rendered sections.

### Checking Inline Images

For each image, verify:

- Exactly one MIME part carries the corresponding Content-ID.
- Content-Type reflects the actual image format.
- Content-Disposition fits an inline resource.
- The HTML body references the matching CID.
- The resource has valid bytes and does not exceed size limits.

### Checking Attachments

For each attachment, verify:

- MIME type is right.
- Content-Disposition is attachment as intended.
- Filename is right and contains no filesystem paths.
- Bytes after decoding match the original file content.
- File does not exceed limits permitted by the application/provider.

## 19. Workflow for Display Testing on Email Clients

An in-memory MIME test cannot fully replace viewing the email on clients. When changing multipart modes or templates, use this workflow:

1. Build a test message containing text/plain, HTML, one inline image, and one PDF attachment.
2. Send to an SMTP sink or an organization-managed test account.
3. Save raw MIME as evidence of the message structure.
4. Open the email on the client versions the product supports.
5. Inspect inline images, text version, attachments, links, layout, and image-blocking mode.
6. If clients differ, compare MIME at sending and receiving ends if infrastructure allows.

Sample test data:

~~~text
Subject: Order Confirmation ORD-TEST-001
Plain text: Includes order code, total amount, and support info
HTML: Includes CID logo and same business information
Inline image: brand-logo.png
Attachment: invoice-ORD-TEST-001.pdf
Recipient: test mailbox
~~~

Never use real customer emails or attachments containing sensitive data during testing. Test data should be synthesized separately and deletable afterward.

### What to Verify Visually

- The logo sits inside the content at the right position, not merely in the attachment list.
- Main content remains readable when images are blocked.
- The PDF can be downloaded and opened.
- Text-only clients have an easy-to-read text version.
- HTML and text parts are not concatenated into two blocks of content.
- Images are not oversized or breaking the layout.
- Links, text colors, and spacing do not rely on images to convey critical information.

## 20. Security and Limits of Multipart Resources

Multipart mode is a way of organizing a message, not a security mechanism. Embedded or attached resources still must be controlled:

- Pull images/files only from sources the application is authorized to read and send.
- Never use filesystem paths supplied directly by users.
- Validate size, actual byte format, and Content-Type.
- Limit the number of inline resources and attachments to prevent oversized emails.
- Do not embed personal data or tokens in images unnecessarily.
- Never log raw MIME, attachment bytes, credentials, or tokens to production logs.
- Control access permissions and retention times of SMTP sinks/test mailboxes.
- Be cautious loading images from external URLs; defend against SSRF, unexpected redirects, and oversized file downloads.

**Do not trust a file extension as proof of format.** A file named logo.png might contain non-PNG bytes. When data originates from users or external systems, validate file contents with an appropriate mechanism before attaching.

## 21. Frequently Asked Questions

**Does an HTML email always need multipart/related?** No. HTML that references no inline resources can be a simple text/html part. Related is useful when HTML has resources such as CID images.

**Does every email with an attachment need mixed-related?** No. An email with only a body and attachment can use mixed. Mixed-related is especially useful when the same message has HTML, inline resources, and independent attachments.

**Why is the boolean true constructor usually sufficient?** MimeMessageHelper's boolean multipart constructor normally selects mixed-related mode by default, which fits many HTML emails with inline elements and attachments. If you want the code to show intent explicitly or need another mode, use the constructor taking a multipart mode.

**Can I add attachments before setText?** Some orders may still produce a message, yet a clear sequence is recommended: setText first, addInline next, then addAttachment. The ordering rule Spring emphasizes directly is that addInline must follow setText.

**Why does a CID image show up as an attachment?** Check Content-ID, Content-Disposition, HTML reference, and part placement inside the related group. Also check the email client, as clients can present inline parts differently.

**What if the CID matches yet the image is still missing?** Inspect raw MIME after serialization, verify the image part exists, content type is right, image bytes are valid, and the message has an appropriate related structure. Then test another client or check whether a gateway altered the MIME.

**Should I create Multipart manually with Jakarta Mail instead of MimeMessageHelper?** Only for special structures the helper cannot satisfy. For common cases, the helper manages alternative, related, mixed, charset, and resources. Building the MIME tree manually increases responsibility for boundaries, Content-ID, disposition, and ordering.

**Can multipart mode fix incompatible CSS?** No. Multipart only organizes MIME parts. CSS/HTML rendering is a separate problem and requires testing on target email clients.

**Does SMTP server acceptance mean clients will display it right?** No. SMTP accepted only means the server at the submission step accepted the message; clients can still filter, block images, or interpret MIME per their own capabilities.

## 22. Principles to Remember

Choose multipart based on **relationships between parts**, not merely part count:

- **Alternative**: plain text and HTML are two versions of the same content.
- **Related**: HTML together with images/resources it references via CID.
- **Mixed**: message body together with independent attachments.
- **Mixed-related**: mixed at root, related group for HTML and inline resources; suitable for emails with HTML, CID images, and attachments.

In Spring Framework Mail, choose the right multipart mode, use setText(plain, html) when two versions are needed, call **setText before addInline**, and then add independent attachments. Inspect MIME after serialize/parse, do not rely on fixed part indices, and test on target email clients whenever displayability is a product requirement.

**A successfully sent message is not guaranteed to display right.** The MIME structure must accurately express alternative content, related resources, and independent files; only then can clients present the message appropriately.
