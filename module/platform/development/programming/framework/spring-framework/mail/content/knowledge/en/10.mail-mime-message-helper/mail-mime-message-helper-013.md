# Inspecting the MIME tree after the helper builds a message

When using **Spring Framework Mail**, calls to **MimeMessageHelper.setText(...)**, **addInline(...)**, and **addAttachment(...)** help create HTML emails, plain-text alternatives, in-body images, and file attachments without manually assembling MIME headers. However, that convenience has a consequence: a developer easily knows **which methods they called**, yet is not necessarily sure **how the resulting MIME tree was actually built**.

That is an important difference. An email may have HTML, a logo, and a PDF in the program yet on receipt suffer display errors, missing attachments, or show images as downloadable files. The cause sometimes lies not in the source data, but in how **multipart/alternative**, **multipart/related**, and **multipart/mixed** parts are nested, how **Content-ID** is set, or the order of operations when preparing the message.

This lesson guides **inspecting the MIME tree after MimeMessageHelper creates a message**: looking at the tree nodes, analyzing each part's headers, reading the structure via the **Jakarta Mail** API, observing the serialized message, and understanding the limits of inspecting an in-memory message. The goal is to know **which structure the mail truly carries**, rather than guessing from helper method names.

## 1. What is a MIME tree?

MIME (*Multipurpose Internet Mail Extensions*) describes how an email carries multiple types of content. A **MimeMessage** is the root node; when the body is **multipart**, it contains multiple **body parts**; each body part can in turn contain another **multipart**.

Example of a simple email:

~~~text
MimeMessage
|
'-- text/plain; charset=UTF-8
      "Hello!"
~~~

Example with two ways to present the same content:

~~~text
MimeMessage
|
'-- multipart/alternative
     |
     +-- text/plain; charset=UTF-8
     |     "You have a new notification."
     |
     '-- text/html; charset=UTF-8
           <p>You have <strong>a new</strong> notification.</p>
~~~

Example with HTML referencing a logo and a PDF file:

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
     |    |    '-- text/html
     |    |
     |    '-- image/png
     |          Content-ID: <logo-1>
     |          Content-Disposition: inline
     |
     '-- application/pdf
           Content-Disposition: attachment
           filename="guide.pdf"
~~~

The last diagram is a **possible MIME structure**, used to illustrate the purpose of **mixed**, **related**, and **alternative** relationships. The actual tree also depends on the **multipart mode**, the **setText** overload, how resources are added, and the mail library implementation/version. Therefore, **you should not assume every email created by the helper has a tree identical to the diagram**.

### One MIME tree, many inspection questions

| Question | What to observe |
| --- | --- |
| Does the email have only one body or multiple parts? | Root **Content-Type**: text/* or multipart/* |
| Are plain text and HTML two alternative choices? | Is there a **multipart/alternative** wrapping the two corresponding parts |
| Which images belong to the HTML content? | **multipart/related**, **Content-ID**, and **cid:** references |
| Is the PDF an attachment or a body part? | **Content-Type**, **Content-Disposition**, **filename** |
| Does the file contain the right bytes? | Part content after decoding transfer encoding |
| Does the outgoing mail format match the in-memory object? | Serialized MIME or raw message |

Key point: **the MIME tree describes packaging and relationships between parts**, not whether the message has been delivered to the inbox.

## 2. Distinguishing multipart types before inspecting

MIME uses each node's **Content-Type** to define the semantic relationship among child parts.

### multipart/alternative: multiple representations of the same message

~~~text
multipart/alternative
    +-- text/plain
    '-- text/html
~~~

Two parts usually convey **the same information** in two formats. The client chooses the version suited to its capabilities and the reader's preferences. Do not treat these as two passages that must be concatenated sequentially when displayed. By common convention, richer versions like HTML are placed after the text version.

If inspection shows plain text says “Please enable HTML” while HTML holds an important verification code, the MIME tree may be technically valid yet the alternative **does not provide equivalent content** for users without HTML.

### multipart/related: parts depending on each other to form one content

~~~text
multipart/related
    +-- text/html
    '-- image/png
          Content-ID: <course-logo>
~~~

HTML may contain:

~~~html
<img src="cid:course-logo" alt="Course logo">
~~~

The image part with **Content-ID: <course-logo>** is a resource related to the HTML content. Seeing **image/png** in the tree alone is not enough; you must verify whether HTML references the exact ID.

An email can also have **alternative** nested inside **related**, to provide both a plain-text fallback and HTML with images. The exact nesting changes depending on how the message was created.

### multipart/mixed: collection of content and attached parts

~~~text
multipart/mixed
    +-- text/plain
    '-- application/pdf
          Content-Disposition: attachment
~~~

This is a simple example of an email with a body and a PDF attachment. If there are also HTML, inline images, or other parts, **mixed** can contain a child multipart tree instead of just a text part. When reviewing the tree, traverse child nodes **recursively**, not just counting root body parts.

### MIME type differs from disposition

A part:

~~~text
Content-Type: image/png
Content-Disposition: inline
Content-ID: <logo-1>
~~~

and a part:

~~~text
Content-Type: image/png
Content-Disposition: attachment; filename="logo.png"
~~~

both have **Content-Type: image/png**, yet different display purposes. **Content-Type** explains the data type; **Content-Disposition** suggests how to present it; **Content-ID** allows inline content referencing.

Headers are hints to the client, **not absolute commands**. Some mail-reading applications can still display inline images as attachments or block fetching/displaying images.

## 3. MimeMessageHelper and the four multipart modes

**MimeMessageHelper** provides modes for creating MIME multipart. They determine the foundational tree shape before adding plain text, HTML, inline resources, and attachments.

| Mode | Structural intent | Points to remember when observing the tree |
| --- | --- | --- |
| **MULTIPART_MODE_NO** | Does not initialize multipart | Fits single-body emails; not used to add multiple MIME parts |
| **MULTIPART_MODE_MIXED** | **multipart/mixed** root | Body, inline, and attachment parts may sit together under mixed; some clients handle inline differently than desired |
| **MULTIPART_MODE_RELATED** | **multipart/related** root | Suitable for grouping content and related resources; attachments may be displayed unexpectedly by some clients |
| **MULTIPART_MODE_MIXED_RELATED** | **multipart/mixed** root with nested **multipart/related** | Separates content/inline group from attachments; usually the convenient choice when having both inline images and attached files |

Initialization example:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

Note: **MULTIPART_MODE_MIXED_RELATED** is a mode that creates the **mixed/related** structure; it does not mean it automatically adds **multipart/alternative** by itself. The alternative structure appears only when there is a need to create multiple presentations of the same body, such as using **setText(plainText, htmlText)**.

### Same content, different modes can create different trees

Suppose the application executes:

~~~java
helper.setText(plainText, htmlText);
helper.addInline("logo-1", logoResource, "image/png");
helper.addAttachment("report.pdf", reportResource);
~~~

With **MIXED_RELATED** mode, a conceptual tree could be:

~~~text
multipart/mixed
|
|-- multipart/related
|    |-- multipart/alternative
|    |    |-- text/plain
|    |    '-- text/html
|    '-- image/png (Content-ID: <logo-1>)
|
'-- application/pdf (attachment)
~~~

In other modes, parts may sit on different nodes or not be organized into a related layer under mixed. **Do not conclude a message is right based solely on total part count**: parent/child relationships matter too.

### Some easily confused overloads

~~~java
new MimeMessageHelper(message, false, "UTF-8");
helper.setText(html, true);
~~~

The **false** parameter in the constructor means **do not enable multipart**; the **true** parameter in **setText** means **this is an HTML body**. A simple HTML email can still be a single **text/html** part, without necessarily having a multipart root.

Conversely:

~~~java
new MimeMessageHelper(message, true, "UTF-8");
helper.setText(plainText, htmlText);
~~~

The **true** parameter in the constructor requests using the helper's suitable default multipart mode; **setText(plainText, htmlText)** creates two content options in the MIME structure. To control the tree more precisely, choose the **multipart mode** explicitly.

## 4. Creating a typical MimeMessage to observe

The following example creates an email with:

- Plain text for fallback.
- HTML content with an image referenced via **cid:**.
- An attached **PDF** file.
- Explicitly declared **From**, **To**, and **Subject** headers.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class CourseMailFactory {

    private final JavaMailSender mailSender;

    public CourseMailFactory(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public MimeMessage createCourseMail(
            String recipient,
            Path logoPath,
            Path guidePath
    ) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("academy@example.test");
        helper.setTo(recipient);
        helper.setSubject("Course materials");

        String plainText = """
                Hello,

                The course materials are attached.
                Please see the file guide.pdf.
                """;

        String htmlText = """
                <html>
                  <body>
                    <h2>Course materials</h2>
                    <p>Please see the file <strong>guide.pdf</strong>.</p>
                    <img src="cid:course-logo" alt="Course logo">
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);
        helper.addInline(
                "course-logo",
                new FileSystemResource(logoPath.toFile()),
                "image/png"
        );
        helper.addAttachment(
                "guide.pdf",
                new FileSystemResource(guidePath.toFile())
        );

        return message;
    }
}
~~~

Here **only the MimeMessage is created and returned**, **without calling send(...)**. That allows inspecting the in-memory object before submitting the mail to SMTP. The order **setText(...) before addInline(...)** matters in standard MimeMessageHelper usage: some email clients and part-building scenarios are prone to display errors if inline resources are added in the wrong order or with wrong references.

The files at **logoPath** and **guidePath** must exist, have read permissions, and remain available until the message is serialized/sent. A MIME part may hold a **DataHandler/Resource** and not have read all byte content at the moment **addAttachment(...)** is called. Therefore, **successfully creating the tree does not prove the file was read successfully when sending**.

### Choosing the inspection method by purpose

There are three complementary levels of observation:

1. **Traverse the MIME object structure** using **Part**, **Multipart**, **BodyPart**, to see node types and metadata of each part.
2. **Serialize the message into raw MIME** and inspect headers, boundaries, transfer encoding, and the real payload generated at serialization time.
3. **Send through mail capture/test SMTP** and view the received message to see if any transport/provider step altered the packaging.

The first two levels do not need a real SMTP connection. The third level helps observe closer to the mail-receiving experience, though it still does not prove every email client will render identically.

## 5. Traversing the MIME tree with the Jakarta Mail API

Basic data types:

| Type | Role |
| --- | --- |
| **MimeMessage** | Email message at the root level |
| **Part** | Common interface of message/body part |
| **Multipart** | Container holding multiple body parts |
| **BodyPart** | A child part inside a multipart |
| **MimeBodyPart** | Common MIME implementation for a body part |
| **Content-Type** | Header describing content type and parameters |

Given a newly created message, you can descend from root to children following this principle:

~~~text
inspect(part):
    print part metadata
    if part is multipart:
        get Multipart
        for each BodyPart:
            inspect(bodyPart)
    if part is message/rfc822:
        can inspect the attached message
    if part is text, image, PDF, ...:
        print only metadata; no need to read all bytes
~~~

Point to note: **Multipart** is not a **Part**. A Part can **contain** a Multipart; Multipart provides **getCount()** and **getBodyPart(index)** to access child parts. When a body part contains another Multipart, the algorithm must recurse rather than only listing the root.

### A tree-printing utility that does not dump sensitive content

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.Arrays;

public final class MimeTreeInspector {

    private MimeTreeInspector() {
    }

    public static void printTree(Part part)
            throws MessagingException, IOException {
        inspect(part, "root", 0);
    }

    private static void inspect(Part part, String path, int depth)
            throws MessagingException, IOException {

        String indent = "  ".repeat(depth);
        String contentId = String.join(
                ", ", safeHeaders(part.getHeader("Content-ID"))
        );
        String transferEncoding = String.join(
                ", ", safeHeaders(
                        part.getHeader("Content-Transfer-Encoding")
                )
        );

        System.out.printf(
                "%s%s type=%s disposition=%s filename=%s"
                + " contentId=%s cte=%s size=%d%n",
                indent,
                path,
                part.getContentType(),
                part.getDisposition(),
                part.getFileName(),
                contentId,
                transferEncoding,
                part.getSize()
        );

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int index = 0; index < multipart.getCount(); index++) {
                    BodyPart child = multipart.getBodyPart(index);
                    inspect(
                            child,
                            path + "." + index,
                            depth + 1
                    );
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nestedMessage) {
                inspect(nestedMessage, path + ".message", depth + 1);
            }
        }
    }

    private static String[] safeHeaders(String[] values) {
        return values == null
                ? new String[0]
                : Arrays.copyOf(values, values.length);
    }
}
~~~

The example only **prints metadata**, without reading or printing each part's body, because attachments can be very large or carry sensitive information. This is an illustrative tool for test data; **do not write raw Content-ID, filenames, or all headers into production logs** when they may contain personal information or internal data.

For an unserialized part, **getSize()** may return **-1** if the implementation does not know the size. The **Content-Transfer-Encoding** header may also not yet be computed or appear in its final form. That does not prove the message is broken; it shows the difference between the **MIME object under construction** and the **prepared/serialized MIME form**.

Additionally, calling **getContent()** on a multipart may ask the library to parse an existing structure. Do not apply the same operation to every binary attachment just to print the tree, as it can pull large payloads into memory.

## 6. Inspecting after saveChanges and serialize

A **MimeMessage** may be in an edited state. In that state, some headers are generated lazily or inferred from **DataHandler**, part content, and MIME attributes. Therefore distinguish:

- **The object tree after helper calls**: reflects the parts and data the application attached.
- **The message after saveChanges()**: updates necessary headers and metadata per Jakarta Mail's mechanism.
- **The data after writeTo(...)**: RFC/MIME representation that can be written to an output stream, with headers, boundaries, and transport-encoded payloads.

Example:

~~~java
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class MimeMessageDump {

    private MimeMessageDump() {
    }

    public static void writeForLocalInspection(
            MimeMessage message,
            Path destination
    ) throws Exception {

        // Prepare MIME headers and metadata at the time of observation.
        message.saveChanges();

        try (OutputStream output = Files.newOutputStream(destination)) {
            message.writeTo(output);
        }
    }
}
~~~

This is an illustrative utility used in **tests or diagnostic environments**. The resulting file can contain the entire message content, addresses, tokens in links, and Base64-encoded attachment bytes; use test data, write to a protected location, and delete per policy. Do not enable raw MIME dumping unconditionally in production.

**saveChanges() does not send email.** It prepares the message according to its current state. Depending on the implementation, writing the message may require opening resource sources, reading attachments, and computing transfer encoding, so serialization can also fail if a resource is no longer readable.

Some headers such as **Message-ID**, **Date**, or boundaries may be generated/adjusted during message preparation and writing. Thus, tests should not depend on **random values or exact header order** unless that is something the application actively controls.

### Why shouldn't raw MIME be compared against a fixed string?

Two messages with equivalent content can differ in:

- Auto-generated **boundary** strings.
- **Message-ID**, date/time, or supplementary headers.
- How long headers are wrapped (*header folding*).
- How **Content-Transfer-Encoding** is chosen (for example quoted-printable or Base64).
- How charset or filename parameters are written.
- The order of certain headers and provider details.

Comparing all raw bytes against a “golden string” can make tests fail due to valid differences unrelated to business requirements. Usually you should **re-parse raw MIME and check structure, MIME types, and decoded content**.

### Reading raw MIME to recognize boundaries

An abbreviated raw copy might look like this:

~~~text
MIME-Version: 1.0
From: academy@example.test
To: learner@example.test
Subject: Course materials
Content-Type: multipart/mixed; boundary="mix-01"

--mix-01
Content-Type: multipart/related; boundary="rel-01"

--rel-01
Content-Type: multipart/alternative; boundary="alt-01"

--alt-01
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Course materials

--alt-01
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<h2>Course materials</h2>
<img src=3D"cid:course-logo">

--alt-01--
--rel-01
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <course-logo>
Content-Disposition: inline

[base64 of image - omitted]

--rel-01--
--mix-01
Content-Type: application/pdf; name="guide.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="guide.pdf"

[base64 of PDF - omitted]

--mix-01--
~~~

This is **illustrative raw MIME**, not a complete message usable to open files: the two bracketed payload blocks are notes and were omitted. Actual boundary values will be generated by the library. The goal of the example is to clarify **nested relationships**:

1. The **mixed** boundary separates the content group from the PDF attachment.
2. The **related** boundary separates displayed content and the inline image.
3. The **alternative** boundary separates plain text from HTML.
4. Each part has its own headers; **Content-Type** and **Content-Transfer-Encoding** do not have to be identical.

**Do not split MIME yourself with string `split("--boundary")`**: boundaries can nest, have closing rules, headers can be folded, and bodies have transfer-encoding layers. Use Jakarta Mail's MIME parser.

## 7. Re-parsing raw bytes: checking a readable format

After serializing, you can construct a **new MimeMessage** from raw data. This simulates the process where a parser must re-interpret the message instead of looking only at the helper object being manipulated.

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class MimeMessageReader {

    private MimeMessageReader() {
    }

    public static MimeMessage parseFromFile(Path emlFile)
            throws Exception {

        Session session = Session.getInstance(new Properties());

        try (InputStream input = Files.newInputStream(emlFile)) {
            return new MimeMessage(session, input);
        }
    }
}
~~~

The example uses an empty Session because the purpose is **reading saved MIME**, requiring no SMTP connection. An object created from an InputStream may retain needed data during parsing depending on implementation; with very large messages, still pay attention to memory and resources.

After re-parsing:

~~~java
MimeMessage parsed = MimeMessageReader.parseFromFile(emlFile);
MimeTreeInspector.printTree(parsed);
~~~

At this point, traversing the tree reflects the structure of the **serialized copy**, helping detect discrepancies between initial intent and actual representation.

### Do not confuse re-parsing with real test sending

Re-parsing an **.eml** file verifies that a MIME parser can interpret the message created by the application. It does not test:

- SMTP accounts and sending permissions.
- Provider size limits.
- **MAIL FROM / RCPT TO / DATA** responses.
- How the target email client renders HTML or inline images.
- Delivery results to the Inbox.

Therefore, MIME tree inspection is a **message structure check**, complementing rather than replacing SMTP integration tests and email client display checks.

## 8. Reading tree output and identifying key nodes

A tree-printing tool may produce conceptual output like:

~~~text
root type=multipart/mixed; boundary=... disposition=null
  root.0 type=multipart/related; boundary=...
    root.0.0 type=multipart/alternative; boundary=...
      root.0.0.0 type=text/plain; charset=UTF-8
      root.0.0.1 type=text/html; charset=UTF-8
    root.0.1 type=image/png
      disposition=inline contentId=<course-logo>
  root.1 type=application/pdf
    disposition=attachment filename=guide.pdf
~~~

This output is illustrative only; index numbers and structure may vary depending on mode and helper version. What to look for is not an exact log string, but **meaningful relationships**.

### Inspecting the main content section

If you called:

~~~java
helper.setText(plainText, htmlText);
~~~

look for a **multipart/alternative** containing two parts **text/plain** and **text/html**. If the code only called:

~~~java
helper.setText(html, true);
~~~

then do not insist on having a text/plain fallback. A message with a single **text/html** body can still be valid per how it was created, even if the product might want to add a fallback for accessibility.

### Inspecting inline images

With:

~~~java
helper.addInline("course-logo", resource, "image/png");
~~~

verify:

1. There is a corresponding **image/png** part.
2. The part has a matching **Content-ID**, for example **<course-logo>**.
3. The HTML content contains **cid:course-logo**.
4. The **multipart/related** relationship matches how the HTML and image part are grouped.
5. The part has a real byte source and can be serialized without error.

If Content-ID is **logo-1** while HTML references **cid:course-logo**, having both parts in the tree still will not help the client find the right image. **Content-ID and cid: must match on the identifier used**, even though the raw header has angle brackets **<...>**.

### Inspecting attachments

With:

~~~java
helper.addAttachment("guide.pdf", pdfResource);
~~~

look for the part with matching metadata:

~~~text
Content-Disposition: attachment; filename="guide.pdf"
Content-Type: application/pdf
Content-Transfer-Encoding: base64
~~~

The **application/pdf** type is the common case when the resource/filename is recognized; some environments or resources without a declared content type may receive **application/octet-stream** or another type. Therefore, tests requiring strictly application/pdf should stem from **data requirements and explicit Content-Type configuration**, not solely from the filename extension.

Note **Content-Transfer-Encoding** may be decided at the serialization stage. For binary files, Base64 is a common choice, yet a mail-receiving parser must use **each part's actual header** to decode, not apply one assumed encoding to all parts.

## 9. Checking decoded payloads, not reading Base64 as text

From raw MIME:

~~~text
Content-Type: application/pdf
Content-Transfer-Encoding: base64

JVBERi0xLjQK...
~~~

If needing to verify the PDF file was not altered, do not compare the verbatim Base64 string against an application-generated string. Base64 line wrapping can vary, while **decoded bytes** can still be identical.

**Part.getInputStream()** returns the part's data through the MIME processing mechanism, usually the stream with **Content-Transfer-Encoding** already decoded when reading a parsed message. Thus, you can obtain attachment bytes from that stream and compute a hash instead of trying to parse raw data with regex.

Example method reading a part's hash:

~~~java
import jakarta.mail.Part;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class MimeAttachmentDigest {

    private MimeAttachmentDigest() {
    }

    public static String sha256(Part part) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[8192];

        try (InputStream stream = part.getInputStream()) {
            int read;
            while ((read = stream.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

In a controlled test, the hash of attachment bytes after parsing can be compared with the hash of the source file. The method uses a buffer to avoid reading the whole file into a large byte array. It assumes the caller already found the right **attachment part**; the example does not yet include logic to walk the tree and select parts by filename/disposition.

Equal hashes prove bytes were preserved across the tested create/serialize/parse path, **not sender signature authentication**, nor do they guarantee the attachment is safe to open. User-supplied attachment data must still go through appropriate format, size, and security verification workflows.

## 10. Automating MIME tree inspection with structural tests

A test can verify the following properties:

- Root is an appropriate **multipart** when there are multiple parts.
- There is a **multipart/alternative** containing **text/plain** and **text/html**.
- There is at least one **image/png** part referenced by Content-ID.
- There is an **application/pdf** part (or configured content type) with **attachment** disposition and expected filename.
- Decoded plain-text and HTML contents contain the necessary business information.
- Attachment bytes after serialize/parse match the source file when the test requires data preservation.

The important thing is **testing structure by semantics**, not hardcoding the index of every part if structures differ by helper/version while still meeting business needs.

### Example of a simple recursive search

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MimePartFinder {

    private MimePartFinder() {
    }

    public static List<Part> findByMimeType(
            Part root,
            String expectedMimeType
    ) throws MessagingException, IOException {

        List<Part> found = new ArrayList<>();
        walk(root, expectedMimeType, found);
        return found;
    }

    private static void walk(
            Part part,
            String expectedMimeType,
            List<Part> found
    ) throws MessagingException, IOException {

        if (part.isMimeType(expectedMimeType)) {
            found.add(part);
        }

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    BodyPart child = multipart.getBodyPart(i);
                    walk(child, expectedMimeType, found);
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nested) {
                walk(nested, expectedMimeType, found);
            }
        }
    }
}
~~~

With the utility above, a test can start:

~~~java
import static org.junit.jupiter.api.Assertions.*;

MimeMessage message = factory.createCourseMail(
        "student@example.test",
        logoPath,
        guidePath
);
message.saveChanges();

assertTrue(message.isMimeType("multipart/mixed"));
assertFalse(
        MimePartFinder.findByMimeType(message, "text/plain").isEmpty()
);
assertFalse(
        MimePartFinder.findByMimeType(message, "text/html").isEmpty()
);
assertFalse(
        MimePartFinder.findByMimeType(message, "image/png").isEmpty()
);
~~~

This is an **illustrative test snippet**, assuming **factory**, **logoPath**, **guidePath**, and corresponding JUnit dependencies exist. It shows how to traverse **without depending on part index**, yet a stricter test still needs to verify **parent/child relationships**, **Content-ID**, **disposition**, **filename**, and content, rather than just seeing a part with the desired MIME type.

### Why is merely counting MIME types not enough?

A message having **text/html** and **image/png** does not guarantee the image is used by HTML. A message having plain and HTML does not guarantee the two parts are placed inside **multipart/alternative**. A message having a PDF does not guarantee the PDF is declared as an **attachment**.

Therefore, important tests should focus on the **right subtrees**:

~~~text
alternative
  -> has plain and HTML as siblings in proper relation

related
  -> HTML in same group with images referenced via cid

mixed
  -> attachment sits outside the alternative/related content group
~~~

If wanting to verify parent/child exactly, a test can build an intermediate structure describing **MIME node, path, type, headers, and children** and assert the corresponding relationships. Do not just search for the string **"multipart/related"** across the entire raw message, as that string can appear in headers, content, or positions not representing the desired relationship.

## 11. Scenarios a MIME tree commonly helps uncover

### HTML present but plain-text version missing

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
helper.setText("<h1>Hello</h1>", true);
~~~

The tree may consist of only one **text/html** part. That matches the call above: **setText(html, true)** does not automatically create a replacement plain-text version. If the product requires a fallback for non-HTML mail readers, initialize an appropriate multipart mode and call **setText(plainText, htmlText)**.

### Image exists in the tree yet does not display in HTML

~~~text
HTML:    <img src="cid:logo-header">
Part:    Content-ID: <logo-footer>
~~~

The two identifiers differ so HTML does not reference the image part properly. In other situations, Content-ID may match yet:

- The image part sits outside the **multipart/related** group the client needs.
- **Content-Type** does not accurately reflect the image type.
- The source file was deleted or unreadable when serializing.
- The email client blocks images or picks a different display method.

**Having all parts does not mean the parts are related properly**, and a valid tree still does not guarantee every client displays identically.

### PDF exists in the tree yet does not appear as an attachment

If the PDF part lacks **Content-Disposition: attachment** or a filename, some email clients may display it differently from intent. When business logic requires an attached file, look for metadata like:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
~~~

In some cases, Content-Type may be **application/octet-stream** if the library did not recognize the file type; clarify what metadata is actually required and whether the file bytes remain intact.

### Counting parts only at the root

A **multipart/mixed** root may have **two direct parts**, yet the first part is a **multipart/related** containing **multipart/alternative** and a logo. Thus, **root.getCount() == 2** does not mean the entire email has only two contents. Recursive traversal is required.

### Transfer encoding headers have not appeared yet

While a message is still being constructed, some headers may be inferred or finalized lazily during **saveChanges()/writeTo()**. Do not treat the absence of **Content-Transfer-Encoding** before serialization as certain proof of an error. Inspect the prepared raw copy and re-parse if needed.

### Filename present yet source file unreadable

**addAttachment(...)** may attach a **Resource/DataHandler** where actual byte reading occurs when the message is written/sent. If a temp file was deleted before serialization, metadata may still appear yet the later payload read fails. Thus distinguish:

1. **Part created** and has metadata.
2. **Resource still available** when the library needs to read.
3. **Message serialized completely**, payload processed successfully.

## 12. Memory, streams, and security when observing the tree

MIME tree inspection should prioritize metadata, avoiding unnecessarily reading entire attachments. A large file can make using **ByteArrayOutputStream** or converting a raw message to a **String** consume lots of RAM; Base64 makes the representation size even larger.

With large attachments, using **getInputStream()** chunk-by-chunk to compute a hash is usually better than loading all bytes onto the heap. With a read-once stream source, remember Jakarta Mail may need to re-read the resource when preparing the message; avoid assuming **InputStreamResource** can be reopened safely like a file or byte-array resource.

Do not share a **mutable MimeMessage** across multiple workers and concurrently call **setText**, **addAttachment**, **saveChanges**, and **writeTo**. It is better to create a separate message object per send task, complete helper operations, and only then observe or send.

### Do not dump raw emails into production logs

A MIME dump can contain sender/recipient addresses, transaction contents, URLs with tokens, filenames, and attached files. **Base64 is not security encryption**; payloads can be restored back to original bytes. If investigation is needed:

- Prefer **mock data**, local mail capture, and files in a protected directory.
- Log only needed attributes such as part type, path in the tree, and part count.
- Mask addresses, identifiers, and sensitive content data before sharing.
- Do not put raw MIME, attachments, or tokens verbatim into default centralized logs.
- Delete test dumps according to data retention policies.

Furthermore, calling **getContent()** on a binary attachment just to know its type can waste memory or resources. A tree-traversal utility should call **getContent()** when descending into **multipart** or nested messages, and for leaves read only metadata unless there is an explicit requirement to inspect the payload.

## 13. Inspecting the MIME tree differs from testing sending and display

After inspecting the MIME structure, you can send the message through a **test SMTP server/mail capture** to view the copy the transport submits. However, verification scope differs at each stage:

| Stage | Can confirm | Cannot conclude by itself |
| --- | --- | --- |
| Traverse object tree | Which parts and metadata the helper created | Whether payload was fully written or SMTP accepted the mail |
| Serialize and re-parse .eml | Parser can read structure, headers, encoding, and data per test | Whether sending infrastructure will accept the mail |
| SMTP test server | Transport successfully submitted message to test environment | Whether real provider will deliver mail to Inbox |
| Open mail in target email client | How one specific client renders HTML, inline images, and attachments | That every client will render identically |
| Provider events / DSN | Evidence of submission, delivery, or bounce in supporting infrastructure | That recipient actually read and understood content |

If the MIME tree in the application is right yet images do not display when the recipient opens the mail, compare the **MIME copy built in the application** with the **raw message on the receiving side**. SMTP gateways or mail servers can add headers like **Received**, **Return-Path**, authentication results, and sometimes alter messages per policy. An email client can also block images even when the MIME tree is right.

**JavaMailSender.send(...)** returning does not mean that MIME tree appeared intact in the Inbox. It is only the step of sending through transport per the API contract at call time.

## 14. Practice scenarios

### Scenario 1: HTML only

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
helper.setText("<h2>Notification</h2>", true);
~~~

**Question:** do you need to look for **multipart/alternative** in the tree?

**Answer:** not required. The code creates only an HTML body. If a plain fallback is also needed, you must create two content versions using the appropriate API.

### Scenario 2: HTML with inline image

~~~text
HTML: <img src="cid:course-logo">
Content-ID: <different-logo>
Content-Type: image/png
~~~

**Question:** does having image/png mean the image will appear?

**Answer:** no. The CID in HTML differs from the image part's Content-ID. Identifiers must match and have an appropriate MIME relationship with the HTML content.

### Scenario 3: Root has two parts

~~~text
multipart/mixed
  +-- multipart/related
  |    +-- multipart/alternative
  |    |    +-- text/plain
  |    |    '-- text/html
  |    '-- image/png
  '-- application/pdf
~~~

**Question:** why does root.getCount() return only 2?

**Answer:** because it counts the two **direct children** of root: related and PDF. To see plain, HTML, and the image, you must descend through the nested multiparts.

### Scenario 4: Two raw emails have different boundaries

Two builds of the same content have different boundary and Message-ID values.

**Question:** did the second build fail?

**Answer:** not necessarily. These values can be auto-generated. Compare structure, meaningful headers, and decoded content instead of comparing the entire raw string literally.

### Scenario 5: Attachment has the right filename yet writeTo fails

**Question:** is checking the MIME tree alone enough?

**Answer:** no. A part having metadata does not guarantee the byte source is still readable. Check resource lifecycle, temporary files, and the serialization stage to determine whether data can actually be supplied.

### Scenario 6: PDF has Content-Type application/octet-stream

**Question:** is it certain the user cannot receive the PDF?

**Answer:** not enough basis. The file may contain the right bytes while the content type was described generically. Check application requirements, attachment disposition, filename, and inspect the decoded payload.

### Scenario 7: HTML has logo yet email client displays it as an attachment

**Question:** is the bug definitely caused by MimeMessageHelper?

**Answer:** cannot conclude yet. Inspect the related tree, Content-ID, cid reference, raw MIME on the receiving side, and how that client handles inline resources. A valid structure can still be displayed differently.

### Scenario 8: Test finds text/plain and text/html

**Question:** is that enough to prove they are two alternative display forms of the same content?

**Answer:** not yet. Verify both belong to a matching **multipart/alternative** relationship and essential content is equivalent, rather than just having two MIME types at arbitrary positions in the tree.

## 15. Mnemonic workflow

~~~text
1. Determine content needs
   -> plain, HTML, alternative, inline, attachment

2. Choose MimeMessageHelper multipart mode
   -> NO / MIXED / RELATED / MIXED_RELATED

3. Complete message construction
   -> setText, addInline, addAttachment
   -> ensure resource sources remain readable

4. Observe MIME tree
   -> root Content-Type and all child parts
   -> are alternative / related / mixed relationships right?
   -> do Content-ID, filename, disposition fit?

5. When needing to confirm complete MIME form
   -> saveChanges
   -> writeTo / serialize
   -> re-parse and inspect metadata, content, bytes

6. When needing to confirm sending/display process
   -> SMTP test capture, raw message on receiving side
   -> email clients and provider delivery events
~~~

**Inspecting the MIME tree after MimeMessageHelper creates a message is inspecting structure, not merely counting parts.** A message needs the right relationships among presentation versions (**alternative**), dependent resources (**related**), and attachments (**mixed**). By traversing **Part/Multipart** recursively, checking **Content-Type/Content-ID/Content-Disposition**, and serializing and re-parsing when needed, developers can catch MIME message issues before sending and distinguish them from SMTP errors or email client behavior.
