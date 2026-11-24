# Combining alternative, related, and mixed

An email may need multiple display formats and multiple types of content at the same time: recipients may read **plain text** or **HTML**, the HTML part may reference inline logos/images, and the email may also carry one or more attachments. In Spring Framework Mail, these needs are packaged using MIME multipart.

The three most important multipart types are **multipart/alternative**, **multipart/related**, and **multipart/mixed**. Each type represents a different relationship between the parts of an email:

- **alternative**: alternative versions of content, such as plain text and HTML.
- **related**: a primary content part together with resources that the content references, such as HTML and images via CID.
- **mixed**: a primary content part together with independent parts such as attached PDF files or spreadsheets.

When an email needs all three capabilities, what matters is **nesting the multiparts according to their exact semantics**. Simply having text/plain, text/html, image/png, and application/pdf parts does not prove the message is right; each part must belong to the proper group so email clients understand their relationships.

This lesson explains how to combine the three multipart types, how to build the email with **MimeMessageHelper**, how to inspect the MIME tree after creation, and common issues when email clients display images or attachments.

## 1. Three Multipart Types Represent Three Different Relationships

### multipart/alternative: Same Content, Multiple Presentations

An email can provide two versions of the same message:

~~~text
multipart/alternative
    +-- text/plain
    |     "Order ORD-1528 has been confirmed."
    |
    '-- text/html
          <p>Order <strong>ORD-1528</strong>
          has been confirmed.</p>
~~~

Plain text provides content that is easy to read in every mail reader; HTML allows headings, labeled links, tables, and richer presentation. These are **two choices for the same content**, not two paragraphs to concatenate when displaying.

Parts in multipart/alternative are normally ordered from the less rich version to the richer version. Therefore, **text/plain usually precedes text/html**. The email client chooses the version matching its capabilities or settings.

If plain text says "payment succeeded" while HTML says "payment pending", the two parts are no longer equivalent presentations. That is a data/template bug, even if the MIME hierarchy is valid.

### multipart/related: Main Content with Dependent Resources

HTML can reference inline images:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

The image can be packaged together with the HTML content inside multipart/related:

~~~text
multipart/related
    +-- text/html
    |     <img src="cid:brand-logo">
    |
    '-- image/png
          Content-ID: <brand-logo>
          Content-Disposition: inline
~~~

The first part of multipart/related is the **root part**; the remaining parts are related resources referenced by the root content. In the example above, HTML is the root and the image is the resource resolved by Content-ID.

**The CID in HTML and the Content-ID of the image must match.** If HTML uses cid:brand-logo while the image part has a different Content-ID, the image may not be found even though the MIME message contains both an HTML part and an image part.

### multipart/mixed: Independent Parts in the Same Email

An email can contain main content and an attached file:

~~~text
multipart/mixed
    +-- text/plain
    |     "The report is attached."
    |
    '-- application/pdf
          Content-Disposition: attachment
          filename="report.pdf"
~~~

Child parts of mixed are distinct components within one message. An attachment is neither an alternative version of the body nor a resource referenced by HTML via CID.

Thus, if an email has a PDF for the recipient to download, the PDF normally belongs in the **mixed** group. If HTML has a logo, the logo belongs in the **related** group with HTML. If both plain and HTML are needed, the two versions belong in the **alternative** group.

## 2. Why Combine and Nest All Three Multipart Types?

Suppose an order confirmation email has these requirements:

1. Have a plain text fallback.
2. Have HTML with an inline logo and product photo.
3. Have an attached PDF invoice.

A common MIME structure for this case:

~~~text
MimeMessage
|
'-- multipart/mixed
     |
     +-- multipart/related
     |    |
     |    +-- multipart/alternative
     |    |    |
     |    |    +-- text/plain
     |    |    |
     |    |    '-- text/html
     |    |
     |    +-- image/png
     |    |     Content-ID: <brand-logo>
     |    |
     |    '-- image/jpeg
     |          Content-ID: <product-photo>
     |
     '-- application/pdf
           Content-Disposition: attachment
           filename="invoice.pdf"
~~~

Reading the tree by relationships:

- Outermost **mixed** groups the email content and the PDF attachment.
- **related** groups the displayable content part together with inline image resources.
- **alternative** provides the plain and HTML versions of the content.
- Image parts are referenced from HTML via CID.
- The PDF sits at the mixed level, separated from inline resources.

This is a valid and clear nesting approach for an email that has body alternatives, inline resources, and attachments. The actual structure is determined by how the message is built, the multipart mode, and the library; inspect the MIME tree after creation instead of guessing solely from the number of helper calls.

### Another Nesting Pattern Can Also Be Valid

In MIME terms, another option is placing **multipart/alternative** on the outside, where the HTML branch is a multipart/related:

~~~text
multipart/mixed
    |
    +-- multipart/alternative
    |    |
    |    +-- text/plain
    |    |
    |    '-- multipart/related
    |         +-- text/html
    |         +-- image/png
    |         '-- image/jpeg
    |
    '-- application/pdf
~~~

In this structure, plain text is one option; the HTML option consists of the HTML root and related images. This is also a meaningful representation: images are needed only for the HTML branch.

The two diagrams show different ways of grouping content. What must be preserved is that **alternative must hold equivalent choices**, **related must group root content with referenced resources**, and **mixed must group independent parts like attachments**. When using the Spring helper, inspect the structure produced by your library version and multipart mode.

## 3. Role of Part Order in Each Multipart Type

Part ordering is not a decorative detail.

| Multipart | First part | Subsequent parts |
| --- | --- | --- |
| **alternative** | Less rich version, usually text/plain | Richer versions, usually HTML at the end |
| **related** | Root part, i.e., main content | Resources referenced by root, such as CID images |
| **mixed** | Main content or content group of the email | Independent parts, usually attachments |

### For alternative

Placing plain text before HTML helps clients choose the suitable version. Do not put two identical copies just to increase part count; each version must have genuine corresponding content.

### For related

The root part must be the content that the related resources serve. If HTML references a logo, HTML needs to be identified as the root of the related group (or inside the alternative root used by the related group depending on the chosen structure). CID images do not automatically become the main body.

### For mixed

Email content should be placed before attachments. This helps clients process the body part and downloadable parts in the usual relationship. Attachments remain independent parts even when they share the same topic as the body content.

## 4. Choosing the Multipart Mode in MimeMessageHelper

Spring provides the common multipart modes:

| Constant | Root structure | Common purpose |
| --- | --- | --- |
| **MULTIPART_MODE_NO** | No multipart created | A simple single body |
| **MULTIPART_MODE_MIXED** | multipart/mixed | Body with attachments |
| **MULTIPART_MODE_RELATED** | multipart/related | Body with inline resources |
| **MULTIPART_MODE_MIXED_RELATED** | mixed root with nested related multipart | HTML with inline resources plus attachments |

For an email needing **alternative + related + mixed**, **MULTIPART_MODE_MIXED_RELATED** is usually the right starting point: mixed at the root to hold attachments, related nested inside to hold content and inline resources. When calling **setText(plainText, htmlText)**, the helper creates alternative content per its API; when calling **addInline(...)**, resources are added to the related group; when calling **addAttachment(...)**, attachments are added to the outer mixed group.

Conceptual diagram:

~~~text
MimeMessageHelper
    |
    +-- setText(plain, html)
    |       -> alternative body
    |
    +-- addInline(cid, resource)
    |       -> related resource
    |
    '-- addAttachment(name, resource)
            -> mixed attachment
~~~

**The multipart mode determines the container structure**, while helper methods populate content into that structure. Simply calling all three methods does not by itself prove the parts were placed in the right relationships; inspect the message after creation.

### Initializing the Helper

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

The second parameter is the multipart mode; the third parameter is the charset for text parts. The UTF-8 charset ensures Vietnamese content is represented properly when the library creates text parts. It does not mean binary files like PNG or PDF are converted to UTF-8.

### Do Not Confuse Multipart with HTML

Multipart only means the message contains multiple MIME parts. It does not automatically create HTML, nor does it automatically create a plain fallback.

- **setText(html, true)** marks the body string as HTML.
- **setText(plainText, htmlText)** provides two alternative content versions.
- **addInline(...)** adds an inline resource.
- **addAttachment(...)** adds an attached file.

A multipart/mixed email might only contain text/plain and a PDF. A simple text/html email might not need multipart at all. Choose the structure based on content relationships, not on the mindset that "more multiparts make a better email".

## 5. Creating an Email with Plain Text, HTML, Inline Images, and PDF

The example below builds an order confirmation email with:

- **Plain text** containing order details and a link to view the order.
- **HTML** with an inline logo and product photo.
- **PDF** as an attached invoice.

Assume the two templates are configured in their respective TemplateEngines. The HTML template references images by CID:

~~~html
<html>
  <body>
    <img src="cid:brand-logo" alt="Store logo">
    <h1>Order Confirmed</h1>
    <p>Hello <span th:text="${mail.recipientName}">customer</span>.</p>
    <p>
      Order:
      <strong th:text="${mail.orderNumber}">ORD-000</strong>
    </p>
    <p>
      Product:
      <span th:text="${mail.productName}">Product</span>
    </p>
    <img src="cid:product-photo" alt="Product photo">
    <p>
      <a th:href="${mail.orderUrl}">View order</a>
    </p>
  </body>
</html>
~~~

The plain text template can be:

~~~text
ORDER CONFIRMED

Hello, [[${mail.recipientName}]].
Order code: [[${mail.orderNumber}]]
Product: [[${mail.productName}]]

View order:
[[${mail.orderUrl}]]

The PDF invoice is attached to this email.
~~~

The plain text interpolation syntax depends on the configured template mode and dialect; the example above illustrates the content idea, and you must use syntax matching your application's text resolver.

In the service example below, the two beans **htmlTemplateEngine** and **textTemplateEngine** must be configured with their respective template modes/resolvers. The **@Qualifier** annotation distinguishes two beans of the same Java type; if the application uses only one TemplateEngine, multiple resolvers or a custom rendering approach fitting the project architecture can be configured.

### Mail Model

~~~java
public record OrderMailModel(
        String recipientName,
        String orderNumber,
        String productName,
        String orderUrl
) {
    public OrderMailModel {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("Missing orderNumber");
        }
        if (orderUrl == null || orderUrl.isBlank()) {
            throw new IllegalArgumentException("Missing orderUrl");
        }

        recipientName =
                recipientName == null || recipientName.isBlank()
                        ? "customer"
                        : recipientName.strip();
    }
}
~~~

The model validates required variables and normalizes the recipient name. In real applications, **orderUrl** must be built from a trusted domain, and **productName** must be rendered through the template engine's HTML escaping mechanism.

### Service Creating the MIME Message

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.util.Locale;
import org.springframework.core.io.Resource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine htmlTemplateEngine;
    private final TemplateEngine textTemplateEngine;

    public OrderMailService(
            JavaMailSender mailSender,
            @Qualifier("htmlTemplateEngine") TemplateEngine htmlTemplateEngine,
            @Qualifier("textTemplateEngine") TemplateEngine textTemplateEngine
    ) {
        this.mailSender = mailSender;
        this.htmlTemplateEngine = htmlTemplateEngine;
        this.textTemplateEngine = textTemplateEngine;
    }

    public void sendOrderConfirmation(
            String recipient,
            OrderMailModel model,
            Resource brandLogo,
            Resource productPhoto,
            Resource invoicePdf,
            Locale locale
    ) throws MessagingException {

        Context context = new Context(locale);
        context.setVariable("mail", model);

        String html = htmlTemplateEngine.process(
                "mail/order-confirmation",
                context
        );
        String plain = textTemplateEngine.process(
                "mail/order-confirmation.txt",
                context
        );

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("orders@example.test");
        helper.setTo(recipient);
        helper.setSubject("Order confirmation " + model.orderNumber());

        // Create the two alternative versions of the body first.
        helper.setText(plain, html);

        // Images referenced by HTML via CID.
        helper.addInline("brand-logo", brandLogo, "image/png");
        helper.addInline("product-photo", productPhoto, "image/jpeg");

        // Invoice is an independent attachment in the mixed group.
        helper.addAttachment(
                "invoice-" + model.orderNumber() + ".pdf",
                invoicePdf,
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

The code illustrates how the APIs work together:

1. The same **OrderMailModel** is placed into the context for both HTML and plain text.
2. **setText(plain, html)** creates the alternative content.
3. **addInline(...)** adds images with Content-IDs matching the CIDs in HTML.
4. **addAttachment(...)** adds the PDF with an explicit Content-Type.
5. **JavaMailSender.send(...)** submits the MIME message via transport.

Here **MULTIPART_MODE_MIXED_RELATED** is used because the email has both inline resources and an attachment. The CID names in the helper are **brand-logo** and **product-photo**, so HTML must reference **cid:brand-logo** and **cid:product-photo** verbatim.

### Why Call setText Before addInline?

When using **MimeMessageHelper**, you should set the text/HTML parts before adding inline resources. Calling in this order lets the helper create the main content first and then attach related resources to the appropriate multipart group. If inline resources are added before HTML content exists, depending on how the structure is built, you may encounter errors or unexpected MIME relationships.

### Why Does the PDF Use addAttachment Instead of addInline?

The invoice PDF needs to be downloaded/opened by the recipient as an attached document, not as an image referenced by HTML via CID. **addAttachment(...)** creates a part with attachment disposition; **addInline(...)** creates a part related to the body, typically referenced via CID.

If you want the recipient to view the PDF via a link inside HTML, generate a secure URL to the document. Attaching a PDF and providing a download link are two different distribution mechanisms.

### Resources Must Remain Readable

Resources passed to the helper must still be available when the message is serialized/sent. Do not delete temporary files or close underlying streams too early after calling **addAttachment(...)** or **addInline(...)**. For single-read sources, ensure the implementation can open streams as required by the library; otherwise, use a more suitable Resource.

## 6. Illustrative Raw MIME Structure

A message created per the example can be conceptually represented as follows:

~~~text
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mixed-01"

--mixed-01
Content-Type: multipart/related; boundary="related-01"

--related-01
Content-Type: multipart/alternative; boundary="alternative-01"

--alternative-01
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Order ORD-1528 has been confirmed.

--alternative-01
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<img src=3D"cid:brand-logo">
<h1>Order Confirmed</h1>

--alternative-01--
--related-01
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brand-logo>
Content-Disposition: inline

[image payload omitted]

--related-01--
--mixed-01
Content-Type: application/pdf; name="invoice-ORD-1528.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice-ORD-1528.pdf"

[PDF payload omitted]

--mixed-01--
~~~

This is an **abbreviated raw MIME snippet to illustrate structure**, not a complete parseable email file because payloads have been omitted. Actual boundaries are generated automatically by the library. Quoted-printable and Base64 values merely illustrate how bytes are represented.

Key things to read:

- Boundary **mixed-01** separates the body-related portion from the PDF.
- Boundary **related-01** separates the main content from inline images.
- Boundary **alternative-01** separates plain text from HTML.
- Header **Content-ID** connects the image with the CID in HTML.
- Header **Content-Disposition: attachment** indicates the PDF is an attached file.

In real raw MIME, boundary names will differ, headers may be folded across lines, filenames may be encoded, and exact ordering or extra headers may vary. Use a MIME parser instead of splitting raw messages manually by boundary strings.

## 7. Inspecting the MIME Tree After the Helper Creates the Message

A message can contain all part types yet still be nested incorrectly. For example:

- Both text/plain and text/html exist, but they are not inside multipart/alternative.
- image/png and Content-ID exist, but the image is not in the appropriate related group.
- application/pdf exists, but the PDF was added as an inline resource instead of an attachment.
- mixed is at the root, but attachments are not at the expected level.

Therefore, inspect **part types, metadata, and parent/child relationships**.

### Traversing Part and Multipart Recursively

Jakarta Mail provides these APIs:

| API | Role |
| --- | --- |
| **Part** | Common interface for a message or a body part |
| **Multipart** | Container holding multiple body parts |
| **BodyPart** | A child part inside a multipart |
| **MimeBodyPart** | MIME implementation of a body part |
| **MimeMessage** | Top-level email message |

A tree traversal method needs to:

1. Print metadata of the current part.
2. If the part is multipart, obtain Multipart and iterate through each BodyPart.
3. If the part is message/rfc822, optionally continue traversing the nested message.
4. Avoid reading the entire binary payload just to print the structure.

Example:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.MessagingException;
import java.io.IOException;

public final class MimeTreePrinter {

    private MimeTreePrinter() {
    }

    public static void print(Part root)
            throws MessagingException, IOException {
        visit(root, "root", 0);
    }

    private static void visit(
            Part part,
            String path,
            int depth
    ) throws MessagingException, IOException {

        String indent = "  ".repeat(depth);
        String[] contentIds = part.getHeader("Content-ID");
        String contentId = contentIds == null
                ? ""
                : String.join(",", contentIds);

        System.out.printf(
                "%s%s type=%s disposition=%s filename=%s cid=%s%n",
                indent,
                path,
                part.getContentType(),
                part.getDisposition(),
                part.getFileName(),
                contentId
        );

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    BodyPart child = multipart.getBodyPart(i);
                    visit(child, path + "." + i, depth + 1);
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nestedMessage) {
                visit(nestedMessage, path + ".message", depth + 1);
            }
        }
    }
}
~~~

The example above prints **Content-Type**, **Content-Disposition**, filename, and Content-ID. It does not dump body text or attachment bytes. In production, metadata such as filenames or Content-IDs can also contain internal information; log only when necessary and in accordance with data protection policies.

### Conceptually Expected Tree

For an email with mixed, related, and alternative, the output may look like:

~~~text
root type=multipart/mixed
  root.0 type=multipart/related
    root.0.0 type=multipart/alternative
      root.0.0.0 type=text/plain
      root.0.0.1 type=text/html
    root.0.1 type=image/png disposition=inline cid=<brand-logo>
    root.0.2 type=image/jpeg disposition=inline cid=<product-photo>
  root.1 type=application/pdf disposition=attachment filename=invoice.pdf
~~~

This is an illustrative tree for the structure described earlier. Boundary names, child indices, and exact nesting may vary depending on library mode/version. When writing tests, define the **structural contract required by the application**, then verify the actual message against that contract.

### Why Checking Only root.getCount() Is Insufficient

If the mixed root has two direct children—one related and one PDF—**getCount()** on the root returns two. The text/plain, text/html, and image parts sit deeper inside related. Counting parts at a single level is not counting all leaves of the tree.

Traverse recursively and use paths like **root.0.0.1** to pinpoint specific parts when investigating.

## 8. Verifying Correct alternative, related, and mixed Relationships

A structural test should examine each group:

### Verifying alternative

In the alternative group, confirm there are:

- A **text/plain** part.
- A **text/html** part.
- Both parts expressing the same business information.
- Plain text placed before HTML per standard ordering rules.

Merely finding those two MIME types on two different branches of the tree is not enough to prove they are alternative choices for each other.

### Verifying related

Confirm:

- The root of the related group is the main content or the alternative group containing the content.
- HTML references the right CIDs.
- Each referenced CID has a corresponding resource part.
- Content-IDs are not duplicated within the same reference scope.
- Image parts have a Content-Type matching their bytes.
- Inline resources were added via **addInline(...)** and reside in the expected related group.

If HTML uses **cid:brand-logo**, the image part normally has the header **Content-ID: <brand-logo>**. The helper handles header syntax; the developer needs to use the same identifier when calling addInline and when writing HTML.

### Verifying mixed

Confirm:

- Root is **multipart/mixed** if that is the intended structure.
- The main content group precedes attachments.
- The PDF has **Content-Disposition: attachment**.
- Filename matches the desired display name.
- The PDF was not mistakenly placed inside related as an inline resource.

### Verifying Content and Bytes

Correct metadata does not prove correct payload. For critical files, read the attachment stream after parsing the message and compare its hash against the source file. For text parts, inspect content after the MIME parser decodes transfer encoding.

Do not compare the entire raw MIME as a fixed string because boundaries, Message-IDs, timestamps, header folding, and transfer encodings can validly change.

## 9. Serializing and Re-Parsing the MIME Message

A MimeMessage can be prepared in memory, yet some headers or part data are only finalized when the message is serialized. To inspect the actual MIME output, call **saveChanges()**, write the message to a file in tests, and parse it back.

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class MimeMessageRoundTrip {

    private MimeMessageRoundTrip() {
    }

    public static void write(MimeMessage message, Path destination)
            throws Exception {
        message.saveChanges();
        try (OutputStream output = Files.newOutputStream(destination)) {
            message.writeTo(output);
        }
    }

    public static MimeMessage read(Path source) throws Exception {
        Session session = Session.getInstance(new Properties());
        try (InputStream input = Files.newInputStream(source)) {
            return new MimeMessage(session, input);
        }
    }
}
~~~

Then:

~~~java
Path eml = Path.of("build/test-mail/order-confirmation.eml");
MimeMessageRoundTrip.write(message, eml);

MimeMessage parsed = MimeMessageRoundTrip.read(eml);
MimeTreePrinter.print(parsed);
~~~

This is a **MIME round-trip** check: serialize the message and parse it back to confirm the structure is readable in MIME format. It does not send an email and does not test SMTP providers or how every email client renders it.

Raw .eml files can contain addresses, transaction content, tokenized links, and full encoded attachments. Create dump files only with test data, store them in a protected location, and delete them per policy. **Base64 is not security encryption**.

## 10. Testing a Message That Has All Three Multipart Types

A good test does not only assert that the message is multipart; it verifies key relationships:

| What to confirm | Evidence in the MIME tree |
| --- | --- |
| Alternative body exists | A multipart/alternative group containing text/plain and text/html |
| Inline image exists | Image part has a Content-ID referenced by HTML |
| Attachment exists | Part has attachment disposition and expected filename |
| Suitable containers exist | Mixed root and related group are in expected positions |
| Consistent content | Plain and HTML share order number, status, amount, URL |
| Payload preserved | Bytes after parsing/decoding match source when required by tests |

### Finding Parts by Type Instead of Fixed Index

With multi-level trees, tests should not assume the PDF is always **root.getBodyPart(1)** if templates can add images or change structure. Traverse recursively to collect parts, then match by **MIME type + disposition + filename**.

Example attachment-finding function:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.MessagingException;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MimePartSearch {

    private MimePartSearch() {
    }

    public static List<Part> findAttachments(Part root)
            throws MessagingException, IOException {
        List<Part> matches = new ArrayList<>();
        walk(root, matches);
        return matches;
    }

    private static void walk(Part part, List<Part> matches)
            throws MessagingException, IOException {

        if (Part.ATTACHMENT.equalsIgnoreCase(part.getDisposition())) {
            matches.add(part);
        }

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    BodyPart child = multipart.getBodyPart(i);
                    walk(child, matches);
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nested) {
                walk(nested, matches);
            }
        }
    }
}
~~~

Then a test can locate the PDF part:

~~~java
List<Part> attachments = MimePartSearch.findAttachments(parsed);

Part invoice = attachments.stream()
        .filter(part -> "invoice-ORD-1528.pdf".equals(part.getFileName()))
        .findFirst()
        .orElseThrow();

assertTrue(invoice.isMimeType("application/pdf"));
assertEquals(Part.ATTACHMENT, invoice.getDisposition());
~~~

The search snippet illustrates finding parts by disposition and filename. For emails with multiple attachment types, also check MIME type, count, content, or hash per each type's contract.

### Verifying alternative Sits Inside the Right related Container

Finding text/plain and text/html anywhere is not enough. When verifying hierarchy, check:

1. Whether the root is multipart/mixed.
2. Whether a child of mixed is multipart/related.
3. Whether the root content of related is multipart/alternative, per the structure chosen by the application.
4. Image parts are siblings inside related with matching Content-IDs.
5. Attachments sit outside the related group at the mixed level.

These tests should be based on the **specific multipart mode and expected structure**. If the application intentionally uses another valid nesting, test against that structure rather than forcing every message to have identical node paths.

### Verifying CIDs

Suppose HTML has:

~~~html
<img src="cid:brand-logo">
~~~

Tests should find an image part with:

~~~text
Content-ID: <brand-logo>
Content-Type: image/png
Content-Disposition: inline
~~~

The Content-ID header usually has angle brackets; the string in the CID URI usually omits them. When comparing, normalize the two representations rather than comparing the raw header against the entire `cid:brand-logo` string.

### Verifying Plain Text Does Not Depend on Images

Plain text cannot display CID images like HTML. The fallback content must convey sufficient information even when all images are omitted:

- Notification name/type.
- Order code, status, amount, or key data.
- Full link if the recipient needs to take action.
- Attachment info if the email includes documents.

Do not leave only a line saying **"Click the button below"** in plain text, because this version has no HTML button.

## 11. Common Mistakes When Combining Multiparts

### Mistake 1: Using multipart/mixed for Everything

If plain text, HTML, images, and PDFs are placed as peer parts inside mixed, email clients may treat each part as an independent component. They will not know plain and HTML are alternative versions, nor that the image is a resource belonging to HTML.

**How to handle:** use alternative for body variants, related for CID resources, and mixed for attachments.

### Mistake 2: Putting the PDF Inside multipart/alternative

A PDF is not an alternative presentation of the body. If a PDF is placed at the same level as plain/HTML inside alternative, clients may treat the PDF as an alternative version of the content and fail to show it as a normal attachment.

**How to handle:** place the PDF in the mixed group outside the content group.

### Mistake 3: Putting Inline Images in mixed as Independent Attachments

The image may appear in the attachment list while HTML cannot reference it by CID or clients fail to treat it as a related resource.

**How to handle:** add images with **addInline(...)**, use Content-IDs matching HTML, and verify the related group.

### Mistake 4: Using addAttachment for Images Meant to Display in HTML

**addAttachment(...)** represents the file as an independent attachment. It does not automatically create a CID resource for an img tag.

**How to handle:** use **addInline(...)** for images referenced by HTML; you can still attach a separate copy of an image if business requirements genuinely call for both.

### Mistake 5: Mismatched CID

HTML references **cid:logo** while the helper adds inline with ID **brand-logo**. The MIME tree may contain the image, yet HTML cannot find the right resource.

**How to handle:** use the same identifier in HTML and the addInline call; avoid generating ad-hoc IDs in two separate places.

### Mistake 6: Calling addInline Before setText

Operation order may leave the helper without a proper main body when attaching inline resources.

**How to handle:** set plain/HTML via setText first, then call addInline and addAttachment.

### Mistake 7: HTML Only, No Plain Fallback

The email may still be valid, yet fails requirements for supporting plain text readers or HTML-restricted environments.

**How to handle:** render a plain version containing all essential information and call the **setText(plain, html)** overload.

### Mistake 8: Plain and HTML Have Different Data

Two templates use separate models or compute different defaults, causing recipients to read one status in plain and another status in HTML.

**How to handle:** use the same validated/normalized mail model for both templates.

### Mistake 9: Attachment Ends Up Inside related

If an attachment is added to the related container, some clients may treat it as a related resource rather than an independent attached file.

**How to handle:** when having both inline resources and attachments, use the appropriate mixed-related mode and verify the attachment is in the mixed group.

### Mistake 10: Incorrect MIME Type on Image or PDF

An image part with a CID but an unsuitable Content-Type may fail to display; a PDF with the right filename but a generic Content-Type may be recognized differently than expected.

**How to handle:** provide explicit MIME types when needed, validate source bytes, and inspect parts after creation.

### Mistake 11: Assuming Helper Mode Always Builds the Exact Same Tree

Nesting details may vary by mode, overload, Spring/Jakarta Mail version, and how parts are added.

**How to handle:** treat mode as an initial structural choice; verify the actual tree using Jakarta Mail APIs or parsed raw MIME.

### Mistake 12: Assuming a Valid MIME Tree Means the Email Was Delivered

Structural checks only confirm the message was constructed as intended. SMTP can still reject it, providers can process it further, and email clients can block images or alter rendering.

**How to handle:** separate MIME verification, SMTP submission checks, delivery/bounce events, and email client display testing.

## 12. What to Check on Email Clients

A valid MIME tree is an important prerequisite, but email clients still retain control over how to present content according to their capabilities and settings.

| Component | What to test |
| --- | --- |
| **Plain text** | Open the message in plain text mode or a non-HTML reader; confirm complete content and URLs |
| **HTML** | Check headings, links, tables, colors, and readability on small screens |
| **Inline image** | Toggle remote image loading off/on; confirm CID images still display when packaged in the message |
| **Attachment** | Confirm the PDF appears as an attachment, the filename is clear, and the file opens |
| **Dark mode** | Check contrast, background, and text when clients invert or adjust colors |
| **Accessibility** | Check alt text, reading order, and that content does not rely solely on color or images |

### Inline Images vs. Remote Images

CID images are packaged inside the MIME message and referenced by HTML via Content-ID. Remote images typically use HTTPS URLs:

~~~html
<img src="https://cdn.example.test/banner.png" alt="Banner">
~~~

The two approaches behave differently:

- **CID images** increase email size because image bytes are inside the message; clients do not need to fetch images from an external URL to obtain the bytes.
- **Remote images** keep the message smaller, though clients may block image loading, URLs can expire, or the image server may be unavailable.
- Neither should hold essential information understandable only visually; always provide equivalent text.

For small logos that must display reliably in emails, CID can be appropriate. For large banners or frequently changing images, remote URLs may be better if privacy and image-loading policies permit.

### Do Not Let Images Determine Message Meaning

If HTML has a green icon meaning "paid", plain text needs a line like **"Status: Paid"**. If a product image fails to load, the product name and order code must still be in the content. Alt text helps assistive technology users understand images, but does not replace all business information.

### Attachments Still Need Separate Verification

A PDF might appear with the right name in the attachment list while its payload is corrupted. Try opening the file in a test environment, compare hashes after MIME decoding if needed, and verify provider size limits.

Do not rely solely on a PDF icon or filename to conclude the file was packaged intact.

## 13. Charset, Transfer Encoding, and Headers in Multipart

When combining multiple parts, each part can have its own Content-Type and Content-Transfer-Encoding.

Example:

~~~text
multipart/alternative
    +-- text/plain; charset=UTF-8
    |      Content-Transfer-Encoding: quoted-printable
    |
    '-- text/html; charset=UTF-8
           Content-Transfer-Encoding: quoted-printable

multipart/related
    '-- image/png
           Content-Transfer-Encoding: base64

multipart/mixed
    '-- application/pdf
           Content-Transfer-Encoding: base64
~~~

Key points to remember:

- **UTF-8** describes how characters are encoded in text parts.
- **quoted-printable** or **base64** describes how bytes are encoded for transport.
- Binary files like PNG/PDF normally use Base64 in MIME.
- Boundaries separate parts; boundaries are generated and managed by the library.
- The Content-ID header assigns an identifier to an inline resource.
- Content-Disposition distinguishes inline parts from attachments per the sender's intent.

Do not manually Base64-encode content before passing it to **setText(...)**. Pass text/HTML strings and Resource bytes to the helper; Jakarta Mail handles transfer encoding when serializing the message.

### Filenames May Need Encoding

Attachment filenames containing Vietnamese diacritics or non-ASCII characters can be represented using appropriate header/parameter encoding mechanisms. Do not manually concatenate filenames into raw MIME headers. Use **addAttachment(...)** with the desired filename and let the library handle encoding/quoting.

If a filename displays incorrectly on one client, inspect the raw MIME header and test another client. You can choose a safe, readable ASCII filename if compatibility with receiving systems is more important than preserving every diacritic.

## 14. Managing Content-IDs and Inline Resources

Each inline image needs a unique CID identifier within the scope of the message. For example:

~~~java
helper.addInline("brand-logo", logoResource, "image/png");
helper.addInline("product-photo-1528", photoResource, "image/jpeg");
~~~

HTML:

~~~html
<img src="cid:brand-logo" alt="Logo">
<img src="cid:product-photo-1528" alt="Product photo">
~~~

Do not use the same CID for two different images. If two HTML elements reference the same CID, clients may display the same resource in both places; if two parts share a CID, resource selection may become inconsistent.

### Content-ID Is Not a File Path

A CID is a content identifier inside the message, not a disk path or download URL. When HTML uses:

~~~html
<img src="cid:brand-logo">
~~~

the email client looks up the part inside the message with the matching Content-ID. It does not access local server files and knows nothing about the Resource path Java used.

### Checking Resource Count

If a template references three CIDs, the message needs all three corresponding resource parts. Conversely, if a message contains many inline images that HTML never uses, those images bloat the email without delivering value to the recipient.

Manage CID lists in a single place shared by templates and Java, such as constants or an email resource definition class, to prevent drift when renaming.

~~~java
public final class OrderMailContentIds {

    public static final String BRAND_LOGO = "brand-logo";
    public static final String PRODUCT_PHOTO = "product-photo";

    private OrderMailContentIds() {
    }
}
~~~

When creating the message:

~~~java
helper.addInline(
        OrderMailContentIds.BRAND_LOGO,
        brandLogo,
        "image/png"
);
~~~

In templates, CIDs must still be written matching the constant value. To avoid repeating strings across multiple templates, you can pass CIDs in the model or use a centrally managed template fragment mechanism.

## 15. Distinguishing MIME Structure from Sending Status

Combining alternative, related, and mixed occurs at the **message construction** layer. Afterward, JavaMailSender submits the message over transport. These stages should not be conflated:

~~~text
Render templates
      |
      v
Build MIME tree
      |
      v
Serialize message
      |
      v
SMTP submission
      |
      v
Provider accepts / rejects
      |
      v
Delivery, bounce or downstream processing
      |
      v
Email client renders chosen content
~~~

| Stage | Question to answer |
| --- | --- |
| Render | Do variables and templates produce correct plain/HTML? |
| MIME construction | Do alternative, related, and mixed have the right relationships? |
| Serialization | Can MIME headers, boundaries, and payloads be written? |
| SMTP submission | Does the server accept the message? |
| Delivery | Does the provider deliver the mail or emit a bounce event? |
| Rendering | Does the client pick the right alternative and display inline resources/attachments as expected? |

A valid MIME tree does not prove the server received the mail. A server returning an acceptance response after DATA also does not prove the recipient opened the message or that the email client rendered every part correctly.

If SMTP reports success yet an image does not show up, inspect the raw MIME on the receiving side and check the client. If a PDF does not arrive, check provider logs, size limits, and delivery status. You do not need to enable full protocol debugging just to answer a question about HTML/CID if the MIME tree and received copy already provide evidence.

## 16. Scenario Exercises

### Scenario 1 — Plain Text and HTML Side by Side in mixed

A message has a multipart/mixed root with children text/plain, text/html, and application/pdf.

**Question:** will clients understand that plain and HTML are two alternative versions?

**Answer:** no alternative relationship is expressed. To provide two alternative presentations, place plain and HTML inside multipart/alternative; that content group along with the attachment can sit under mixed.

### Scenario 2 — HTML References an Image by CID

HTML uses **cid:logo-main**, while the image part has Content-ID **<logo-footer>**.

**Question:** why does the image not show up?

**Answer:** the CIDs do not match. Use the exact same identifier in HTML and in the addInline call.

### Scenario 3 — Email Has Plain, HTML, Logo, and PDF

**Question:** which multipart types need to appear?

**Answer:** alternative for plain/HTML, related for content and logo, and mixed to group the body with the PDF attachment. A common structure is mixed on the outside, related inside, and alternative as the body of related.

### Scenario 4 — PDF Added via addInline

**Question:** why might the PDF not appear as an attachment?

**Answer:** addInline creates a resource related to the content, typically referenced via CID. A PDF meant for separate download should use addAttachment.

### Scenario 5 — Email Has Only One HTML Body

**Question:** is creating multipart/alternative mandatory?

**Answer:** no. If only an HTML body is needed, setText(html, true) may be sufficient. Alternative is needed when you want to provide an alternative plain text version.

### Scenario 6 — Two image/png Parts Exist Without CIDs

**Question:** can HTML reference the images via cid?

**Answer:** not if the parts lack corresponding Content-IDs. Add inline resources with IDs and reference the matching CIDs in HTML.

### Scenario 7 — Mixed Root Has Two Children

One child is related containing alternative and two images; the other child is a PDF.

**Question:** why does getCount() return two even though the email has five leaf parts?

**Answer:** getCount() only counts direct child parts of the container being called. You must traverse recursively to see the entire tree.

### Scenario 8 — MIME Tree Is Valid, Yet Outlook Displays Image as Attachment

**Question:** can we conclude the helper built it wrong?

**Answer:** not yet. Check Content-ID, Content-Disposition, the related structure, and the received raw message. Then test on target client versions because rendering behavior can differ.

### Scenario 9 — Plain Text Has No URL

HTML has a **View order** button, while plain only says "click the button below".

**Question:** is the fallback sufficient?

**Answer:** no. Plain text needs the full URL or actionable alternative instructions.

### Scenario 10 — Attachment Appears Inside related

**Question:** could this structure make clients treat the file as an inline resource?

**Answer:** yes. When having both inline images and attachments, use mixed-related to separate the related resource group from independent attachments, and verify the actual MIME tree.

## 17. Workflow for Creating and Verifying Multi-Format Emails

~~~text
1. Define content
   -> plain fallback
   -> HTML body
   -> inline images
   -> file attachments

2. Prepare data
   -> validate required variables
   -> normalize optional values
   -> build safe URLs and filenames

3. Render
   -> use the same model for plain and HTML
   -> verify HTML escaping

4. Build MIME message
   -> MIXED_RELATED
   -> setText(plain, html)
   -> addInline(CID, resource, type)
   -> addAttachment(filename, resource, type)

5. Inspect tree
   -> mixed contains body group and attachments
   -> related contains body and inline resources
   -> alternative contains plain and HTML
   -> CID, disposition, filename, and content type are correct

6. Check serialization and sending
   -> saveChanges/writeTo in tests if needed
   -> re-parse MIME
   -> SMTP test capture

7. Check receiving side
   -> plain/HTML rendering
   -> CID images
   -> attachments and size
~~~

A multi-format email should be tested across multiple layers. Template tests verify content; MIME tests verify the tree; SMTP capture verifies the message submitted in a test environment; email clients verify actual rendering.

**Combining alternative, related, and mixed** expresses three distinct relationships within the same email: alternative supplies content versions, related connects content to inline resources, and mixed groups content alongside independent attachments. With Spring Framework Mail, **MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED**, **setText(plain, html)**, **addInline(...)**, and **addAttachment(...)** provide a convenient foundation for constructing messages. Always inspect the MIME tree and serialized output to confirm actual part relationships, then test on target email clients before considering the receiving experience complete.
