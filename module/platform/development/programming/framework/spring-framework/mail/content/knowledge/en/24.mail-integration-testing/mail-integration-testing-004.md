# Verifying the MIME Tree on a Test Server

## 1. Why Do We Need to Test the Actual MIME Structure?

In **Spring Framework Mail**, many applications use **JavaMailSender**, **MimeMessage**, and **MimeMessageHelper** to send HTML emails, plain-text alternatives, inline images, and attachments. An email may be constructed without errors, **send(...)** may be called, and even the SMTP server may return success, yet the **MIME (Multipurpose Internet Mail Extensions)** structure can still be wrong.

For example:

- An email has both plain text and HTML, yet the two parts are not inside **multipart/alternative**.
- A logo image is added using **addAttachment(...)** instead of **addInline(...)**, causing email clients to display it as an attachment.
- The HTML uses **src="cid:brand-logo"** yet the image part lacks the matching **Content-ID**.
- An attachment is placed inside the **multipart/related** branch meant for email content rather than the proper attachment branch.
- Vietnamese subjects and bodies have the wrong charset or are compared as raw MIME-encoded strings.
- Bcc recipients are accidentally added to To/Cc or appear inside the MIME DATA transmitted to recipients.

**Unit tests with Mockito** can prove a service calls the right methods on **MimeMessageHelper** or builds a **MimeMessage** in memory. However, they do not fully prove the transport layer transmitted the expected MIME tree. For those requirements, you need **integration testing via a test SMTP server**, followed by reading back the message the server actually received.

The goal of this guide is to build tests verifying **MIME tree structure**, **parent-child relationships between multiparts**, **Content-Type**, **Content-Disposition**, **Content-ID**, decoded content, and security/compatibility edge cases.

## 2. What Is a MIME Tree?

Modern email is not necessarily a single block of text. MIME organizes a message into a **tree of parts**:

~~~text
MimeMessage
    |
    +-- BodyPart 1
    |     |
    |     +-- BodyPart 1.1
    |     +-- BodyPart 1.2
    |
    +-- BodyPart 2
          |
          +-- ...
~~~

A **leaf part** can contain plain text, HTML, images, PDFs, or binary data. A **container part** has Content-Type **multipart/...** and holds multiple child body parts.

Common subtypes:

| MIME Type | Primary Meaning |
|---|---|
| **text/plain** | Plain text content |
| **text/html** | HTML content of the email |
| **multipart/alternative** | Alternative representations of the same content, usually plain text and HTML |
| **multipart/related** | Main content together with dependent resources such as CID-referenced images |
| **multipart/mixed** | Collection of independent parts, commonly used when attachments are present |
| **image/png** | PNG image; may be inline or an attachment depending on metadata/structure |
| **application/pdf** | PDF content, typically an attachment |

**Content-Type** indicates the part type. **Content-Disposition** specifies presentation such as inline or attachment. **Content-ID** allows other parts, such as HTML, to reference related MIME resources.

A valid MIME tree does not merely need to "contain all the files"; it must also **place the parts in the right relationship to one another**.

## 3. Typical MIME Tree Example for an HTML Email with Logo and PDF

Suppose we need to send an email containing:

- A plain-text version for clients that do not support HTML.
- An HTML version referencing a logo via CID.
- An inline PNG image.
- A PDF attachment.

A typical structure is:

~~~text
MimeMessage
Content-Type: multipart/mixed
|
+-- Part A: multipart/related
|   |
|   +-- Part A.1: multipart/alternative
|   |   |
|   |   +-- Part A.1.1: text/plain; charset=UTF-8
|   |   |
|   |   +-- Part A.1.2: text/html; charset=UTF-8
|   |                     |
|   |                     +-- HTML: src="cid:brand-logo"
|   |
|   +-- Part A.2: image/png
|                   Content-ID: <brand-logo>
|                   Content-Disposition: inline
|
+-- Part B: application/pdf
            Content-Disposition: attachment
            filename="guide.pdf"
~~~

The structure above illustrates the common organization produced by **MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED** in Spring.

Meaning:

1. The outermost **multipart/mixed** groups the email body and attachments.
2. **multipart/related** groups HTML content with the resources needed to render that content.
3. **multipart/alternative** groups the plain-text and HTML variants as alternative representations.
4. **image/png** carries the Content-ID matching the **cid:** URL in HTML.
5. **application/pdf** resides on the attachment branch instead of being mixed into the HTML branch.

In practice, arrangement may vary by **multipart mode**, library version, added parts, and how MIME is normalized. Therefore, **tests should verify the necessary structural semantics**, rather than blindly asserting that every part always sits at index 0, 1, or 2.

## 4. Why Read Emails Back from a Test SMTP Server?

A unit test typically follows the flow:

~~~text
MailService
   |
   v
Mock JavaMailSender
   |
   v
ArgumentCaptor<MimeMessage>
   |
   v
   Assert on pre-send object
~~~

This approach is useful for testing message-building logic, yet skips SMTP transport and can miss:

- **MimeMessage.saveChanges()** execution and header preparation at send time.
- How **Content-Transfer-Encoding** is selected and decoded.
- Header modifications applied by the Jakarta Mail SMTP transport.
- How MIME DATA is transmitted over the SMTP protocol.
- Subtle differences between the pre-send object and the message actually received by the server.

Integration testing:

~~~text
JUnit test
    |
    v
Real Spring Mail service
    |
    v
Real JavaMailSenderImpl
    |
    | SMTP over localhost
    v
SMTP test server
    |
    | Capture MIME DATA
    v
Received MimeMessage
    |
    v
MIME tree walker + assertions
~~~

In this flow, **no emails are sent to the Internet**. The test server can run inside the same JVM or in a test container, capturing the email contents for the test to read and inspect.

The benefit is verifying most of the chain **application -> Spring Mail -> Jakarta Mail -> SMTP -> receiving server**, rather than checking only the pre-transport object.

## 5. Choosing a Test SMTP Server

Commonly used options:

| Option | Strengths | Caveats |
|---|---|---|
| **GreenMail** | Embedded SMTP server, start/stop in JUnit and read received `MimeMessage` objects | Must choose a version compatible with the application's Jakarta Mail |
| **Mailpit or MailHog** | SMTP capture server with web UI/API for viewing messages | Typically requires a process/container and client API to fetch mail |
| **SubEthaSMTP/Wiser** | Embedded SMTP test server able to capture received messages | Must verify compatible versions and APIs |
| **ESP sandbox** | Can test real provider behavior | Depends on accounts, quotas, network, and provider policies |

In the examples below, **GreenMail** is used to test directly inside the JVM with JUnit. This is an illustrative choice; the principles for traversing **MimeMessage/Multipart/BodyPart** apply equally when messages are retrieved from Mailpit or another SMTP sandbox.

### Tool Selection Criteria

A server suitable for verifying MIME trees should:

- Accept SMTP submissions from the system under test.
- Let you read back **the message content received by the server**, not only the object passed into a mock.
- Preserve **Content-Type** metadata, MIME boundaries, Content-ID, and attachments.
- If Bcc/envelope verification is needed, observe **SMTP RCPT TO** independently of MIME headers.
- Start and clean up in isolation between tests.
- Require no production credentials or connections to real users.

## 6. Dependencies and Jakarta Mail Compatibility

Example with modern Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.icegreen:greenmail:2.1.0'
}
~~~

This is an example GreenMail version from the **2.x** branch for Jakarta Mail environments. When applying to a real project, select a version compatible with the **Spring Boot, Spring Framework, Jakarta Mail, and JDK** versions in use.

**Namespace warning:** Spring Framework 6/Spring Boot 3 uses **jakarta.mail.***; older test libraries may still use **javax.mail.***. Mixing the two namespaces causes compile errors or type mismatches despite identical class names.

If your project uses an older Spring/Jakarta Mail stack, adjust dependencies accordingly. The examples below use **jakarta.mail**.

## 7. Organizing a Reliable Integration Test

Instead of depending on an externally installed SMTP server, start and stop the server within the JUnit lifecycle:

~~~text
@BeforeEach
    |
    +-- Create GreenMail server on localhost
    +-- Start SMTP listener
    +-- Create test recipient mailbox
    +-- Create JavaMailSenderImpl pointing to that server

@Test
    |
    +-- Call service to build/send email
    +-- Wait for SMTP server to receive message
    +-- Read MimeMessage from GreenMail
    +-- Traverse MIME tree
    +-- Assert structure and content

@AfterEach
    |
    +-- Stop SMTP server
~~~

The example below uses **ServerSetupTest.SMTP** - a predefined GreenMail test setup. With this setup, the port may be a library-fixed port, so if CI runs multiple tests in parallel you may need a **dynamic port** or a dedicated port per test instance. Never use a fixed-port test SMTP server carelessly when multiple suites share an environment.

## 8. Preparing Testable Fixtures

The example will construct:

| Component | Test Value |
|---|---|
| To | customer@localhost |
| From | notices@example.com |
| Subject | Hóa đơn ORD-123 — đã thanh toán |
| Plain text | Hóa đơn ORD-123 đã được thanh toán. |
| HTML | An HTML snippet containing src="cid:brand-logo" |
| Inline image | Test PNG file at mail/logo.png |
| Attachment | Test PDF file at mail/guide.pdf |

Place small fixtures in the test resources directory:

~~~text
src/test/resources/
└── mail/
    ├── logo.png
    └── guide.pdf
~~~

Use small, valid test files containing no customer data. For MIME tree structure tests, **large attachments** or production documents are unnecessary.

### Why Use Real Binary Fixtures?

If you create an arbitrary byte array and label it **image/png**, you can test the MIME wrapper but cannot verify the payload is a renderable PNG image. Real PNG/PDF fixtures give stronger test signal when inspecting content types, decoded bytes, or how mail clients handle them.

However, do not turn a MIME tree integration test into a detailed image/PDF rendering test. Client-side decoding and display belong to a different layer.

## 9. Creating a MimeMessage with Plain Text, HTML, Inline Image, and Attachment

A sending method using Spring Mail APIs:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class InvoiceMailService {

    private final JavaMailSender sender;

    public InvoiceMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendInvoice() throws MessagingException {
        MimeMessage message = sender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("notices@example.com");
        helper.setTo("customer@localhost");
        helper.setSubject("Hóa đơn ORD-123 — đã thanh toán");

        String plainText =
                "Hóa đơn ORD-123 đã được thanh toán.";

        String htmlText = """
                <html lang="vi">
                  <body>
                    <h1>Hóa đơn ORD-123</h1>
                    <p>Đơn hàng đã được thanh toán.</p>
                    <img src="cid:brand-logo" alt="Store logo">
                  </body>
                </html>
                """;

        // Set text/HTML before adding inline resources.
        helper.setText(plainText, htmlText);

        helper.addInline(
                "brand-logo",
                new ClassPathResource("mail/logo.png"),
                "image/png"
        );

        helper.addAttachment(
                "guide.pdf",
                new ClassPathResource("mail/guide.pdf"),
                "application/pdf"
        );

        sender.send(message);
    }
}
~~~

Key points to note:

1. **MULTIPART_MODE_MIXED_RELATED** explicitly builds the right structure when both attachments and inline resources are present.
2. **setText(plainText, htmlText)** produces two alternative content variants. Recipients do not need to see both simultaneously.
3. **addInline("brand-logo", ...)** registers the resource with a Content-ID so HTML can reference it via **cid:brand-logo**.
4. **addAttachment(...)** adds an independent file; never use it instead of `addInline` for a logo.
5. **ClassPathResource** can supply a fresh InputStream whenever MIME content is re-read; avoid single-use streams for resources that may be read multiple times.
6. **sender.send(message)** flows through real Jakarta Mail transport instead of merely being recorded by Mockito.

**Call order:** When using `MimeMessageHelper` with inline resources, call **setText(...) before addInline(...)** per Spring guidance. This helps the helper construct proper MIME relationships and prevents misplaced content/resource parts.

## 10. Starting GreenMail and Wiring JavaMailSenderImpl

Example of a self-managed JUnit 5 SMTP test server integration test:

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetupTest;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSenderImpl;

import static org.junit.jupiter.api.Assertions.*;

class InvoiceMimeTreeIT {

    private GreenMail greenMail;
    private InvoiceMailService service;

    @BeforeEach
    void setUp() {
        greenMail = new GreenMail(ServerSetupTest.SMTP);
        greenMail.start();

        greenMail.setUser(
                "customer@localhost",
                "customer",
                "test-only-password"
        );

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(ServerSetupTest.SMTP.getPort());
        sender.setDefaultEncoding("UTF-8");

        service = new InvoiceMailService(sender);
    }

    @AfterEach
    void tearDown() {
        if (greenMail != null) {
            greenMail.stop();
        }
    }

    @Test
    void receivesInvoiceAsMimeMessage() throws Exception {
        service.sendInvoice();

        assertTrue(
                greenMail.waitForIncomingEmail(5000, 1),
                "SMTP test server did not receive the email"
        );

        MimeMessage[] received = greenMail.getReceivedMessages();
        assertEquals(1, received.length);

        MimeMessage actual = received[0];

        assertEquals(
                "Hóa đơn ORD-123 — đã thanh toán",
                actual.getSubject()
        );
        assertTrue(
                actual.isMimeType("multipart/mixed"),
                "Email must have a multipart/mixed branch"
        );
    }
}
~~~

This illustrates an initial check. The following sections build on **actual** to traverse and verify the entire MIME tree.

### Why Not Use a Mock in This Test?

In the example above, **JavaMailSenderImpl** opens a real SMTP connection to **GreenMail** on localhost. The test does not merely check that `send` was invoked; it requires the server to receive wire data before analyzing the message.

### Watch Out for Fixed Test Ports

**ServerSetupTest.SMTP** uses a predefined GreenMail test port configuration. It is convenient for illustration, yet can cause collisions if multiple tests or CI workers run in parallel on the same host. In a large suite:

- Use an OS-allocated dynamic port and query the actual listening port via your GreenMail version's API; or
- Assign a dedicated port per test instance/container; or
- Use a JUnit extension/Testcontainers with lifecycle and port-mapping management.

Do not pick an arbitrary hardcoded number and assume the port is guaranteed to be free.

### Notes on Test Accounts

GreenMail can manage internal mailboxes and users. The address **customer@localhost** and password in the example belong solely to the test server, not real email accounts. SMTP tests must never use production provider credentials.

## 11. Verifying SMTP Receipt Before Traversing MIME

Do not start by inspecting **multipart** before verifying the server received the message. If DNS, TCP, or test configuration prevented delivery to the server, downstream assertions will create noise.

Recommended sequence:

~~~text
service.sendInvoice()
       |
       v
GreenMail.waitForIncomingEmail(...)
       |
       +-- False -> transport / setup / timeout / mailbox error
       |
       v
getReceivedMessages()
       |
       +-- Wrong count -> missing, duplicate, or shared mailbox
       |
       v
getSubject(), getFrom(), getRecipients()
       |
       v
Parse MIME tree
~~~

If a test times out, check:

- Did **send(...)** throw a `MailException`?
- Was the server started before the sender was called?
- Do the sender's host/port match the test listener?
- Was the recipient accepted by the test server?
- Is another test sharing the same server or port?
- Did the test assume the wrong received message count when sending to multiple mailboxes?

**Never adjust MIME assertions to hide SMTP setup errors.** Those two error classes live at different layers.

## 12. Reading MimeMessage Content-Type Properly

Jakarta Mail allows:

~~~java
String rawContentType = actual.getContentType();

boolean isMixed =
        actual.isMimeType("multipart/mixed");
~~~

An actual Content-Type might look like:

~~~text
multipart/mixed;
  boundary="----=_Part_17_123456789.1762920000000"
~~~

The **boundary** string is generated to delimit MIME parts and normally changes across message creations.

Avoid writing tests like:

~~~java
assertEquals(
        "multipart/mixed",
        actual.getContentType()
);
~~~

The test above can fail because `Content-Type` also includes parameters like **boundary** or charset. To check the MIME type, use:

~~~java
assertTrue(actual.isMimeType("multipart/mixed"));
~~~

If you need to inspect specific parameters, use a parser such as **jakarta.mail.internet.ContentType** or an equivalent API; never split `Content-Type` naively on semicolons when values may contain quotes.

### MIME Types Are Case-Insensitive

MIME types and subtypes are syntactically case-insensitive. **Part.isMimeType(...)** is preferable to comparing Strings against one specific casing.

## 13. Traversing the MIME Tree with Jakarta Mail

Core APIs:

- **jakarta.mail.Part**: interface representing a MIME part, holding Content-Type, disposition, filename, headers, etc.
- **jakarta.mail.Multipart**: container holding multiple `BodyPart` items.
- **jakarta.mail.BodyPart**: a child component inside a `Multipart`.
- **jakarta.mail.internet.MimeMessage**: the root message, which is also a `Part`.

A recursive traversal method:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MimeTree {

    private MimeTree() {}

    public static List<Part> flatten(Part root)
            throws Exception {
        List<Part> all = new ArrayList<>();
        visit(root, all, 0);
        return List.copyOf(all);
    }

    private static void visit(
            Part part,
            List<Part> all,
            int depth
    ) throws Exception {
        if (depth > 32) {
            throw new IllegalStateException(
                    "MIME tree exceeded test depth limit"
            );
        }

        all.add(part);

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (!(content instanceof Multipart multipart)) {
                throw new IllegalStateException(
                        "Multipart part did not return Multipart"
                );
            }

            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                visit(child, all, depth + 1);
            }
        }
    }
}
~~~

This is a **test helper**, not a general-purpose MIME parser hardened against arbitrary malicious payloads. For external MIME, also bound total part count, payload size, and processing time. In integration tests generated by your own application, depth limits and small fixtures prevent oversized traversal.

### Why Recurse Only When the Part Is Multipart?

A leaf such as **image/png** or **application/pdf** has no child `BodyPart` items under the same mechanism. For nested **message/rfc822** emails, an application may need an extra parsing branch. Tests here focus on MIME trees sent via `MimeMessageHelper` and do not assume every MIME type is multipart or text.

## 14. Printing MIME Structure for Diagnostics

In tests, you can generate a structural summary **containing no body content or sensitive data**:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public static void printStructure(Part part, int depth)
        throws Exception {
    String indent = "  ".repeat(depth);

    System.out.println(
            indent
            + part.getContentType()
            + " | disposition=" + part.getDisposition()
            + " | filename=" + part.getFileName()
    );

    if (part.isMimeType("multipart/*")) {
        Multipart children = (Multipart) part.getContent();

        for (int i = 0; i < children.getCount(); i++) {
            printStructure(children.getBodyPart(i), depth + 1);
        }
    }
}
~~~

Use this function only for **test fixtures**. With real emails, filenames, Content-IDs, or metadata can still carry personal data and must be filtered/masked before production logging.

Never dump the full **MimeMessage.writeTo(System.out)** in routine logs; bodies, attachments, tokens, and real addresses could be exposed.

## 15. Modeling the Tree to Verify Parent-Child Relationships

**MimeTree.flatten(...)** suffices to tell whether a MIME type is present. However, it cannot distinguish:

~~~text
Valid:
  multipart/mixed
    -> multipart/related
        -> multipart/alternative

Wrong target:
  multipart/mixed
    -> multipart/alternative
    -> multipart/related
~~~

Both trees above contain the same **mixed**, **related**, and **alternative** subtypes, yet their relationships differ. An integration test should be able to verify that **alternative is a descendant of related** and **the attachment sits outside the related group**.

You can build a `Node` model for tests:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public final class MimeNodes {

    private MimeNodes() {}

    public record Node(Part part, List<Node> children) {

        public boolean isType(String mimeType)
                throws MessagingException {
            return part.isMimeType(mimeType);
        }

        public List<Node> all() {
            List<Node> nodes = new ArrayList<>();
            nodes.add(this);
            for (Node child : children) {
                nodes.addAll(child.all());
            }
            return List.copyOf(nodes);
        }

        public Optional<Node> first(String mimeType)
                throws MessagingException {
            for (Node node : all()) {
                if (node.isType(mimeType)) {
                    return Optional.of(node);
                }
            }
            return Optional.empty();
        }

        public List<Node> directChildren(String mimeType)
                throws MessagingException {
            List<Node> result = new ArrayList<>();
            for (Node child : children) {
                if (child.isType(mimeType)) {
                    result.add(child);
                }
            }
            return List.copyOf(result);
        }
    }

    public static Node read(Part part) throws Exception {
        return read(part, 0);
    }

    private static Node read(Part part, int depth)
            throws Exception {
        if (depth > 32) {
            throw new IllegalStateException(
                    "MIME tree depth exceeded"
            );
        }

        List<Node> children = new ArrayList<>();
        if (part.isMimeType("multipart/*")) {
            Multipart multipart = (Multipart) part.getContent();
            if (multipart.getCount() > 100) {
                throw new IllegalStateException(
                        "MIME multipart has too many parts in test"
                );
            }
            for (int i = 0; i < multipart.getCount(); i++) {
                children.add(
                        read(multipart.getBodyPart(i), depth + 1)
                );
            }
        }

        return new Node(part, List.copyOf(children));
    }
}
~~~

The **IOException** import in the example is not strictly required when the method declares **throws Exception**, though it helps if declaring narrower checked exceptions. This model intentionally handles nested multiparts only and does not parse `message/rfc822` as an additional branch.

For email data from untrusted sources, also cap **total node count, MIME payload size, and processing time**, not just the part count of each individual multipart.

## 16. Asserting the mixed -> related -> alternative Structure

Once GreenMail has received the message:

~~~java
MimeNodes.Node root = MimeNodes.read(actual);

assertTrue(root.isType("multipart/mixed"));

MimeNodes.Node related = root
        .first("multipart/related")
        .orElseThrow(() -> new AssertionError(
                "Missing multipart/related"
        ));

MimeNodes.Node alternative = related
        .first("multipart/alternative")
        .orElseThrow(() -> new AssertionError(
                "Alternative is not inside the related branch"
        ));

assertTrue(
        alternative.first("text/plain").isPresent(),
                "Missing plain text inside alternative"
);
assertTrue(
        alternative.first("text/html").isPresent(),
                "Missing HTML inside alternative"
);
~~~

These assertions verify:

1. The root has MIME type **multipart/mixed**.
2. The tree contains a **multipart/related** branch.
3. Inside `related` is a **multipart/alternative**.
4. Both plain text and HTML reside under `alternative`.

If strict **direct parent-child relationships** are required, use:

~~~java
assertEquals(
        1,
        root.directChildren("multipart/related").size()
);

assertEquals(
        1,
        related.directChildren("multipart/alternative").size()
);
~~~

Direct relationships fit when the application's MIME contract mandates the exact tree produced by **MULTIPART_MODE_MIXED_RELATED**. If an extra valid wrapper container from a library or provider is acceptable, checking descendant relationships may suffice.

**Do not check only part count:** a MIME root with two parts does not prove one is `related` and the other is the PDF. Check their types and positions.

## 17. Verifying Plain Text and HTML Content

From the `alternative` node, retrieve the text parts:

~~~java
MimeNodes.Node plainNode = alternative
        .first("text/plain")
        .orElseThrow();

MimeNodes.Node htmlNode = alternative
        .first("text/html")
        .orElseThrow();

String plainText =
        (String) plainNode.part().getContent();

String htmlText =
        (String) htmlNode.part().getContent();

assertEquals(
        "Hóa đơn ORD-123 đã được thanh toán.",
        plainText
);

assertTrue(
        htmlText.contains("<h1>Hóa đơn ORD-123</h1>")
);
assertTrue(
        htmlText.contains("cid:brand-logo")
);
~~~

For text parts created and read by Jakarta Mail, **getContent()** typically returns a String already decoded per its charset. This comparison is far better than scanning raw MIME for HTML strings inside data that may be quoted-printable or base64 encoded.

### Why Not Assert the Entire HTML String Unnecessarily?

If templates automatically insert whitespace, line breaks, or minor attributes, comparing the entire HTML string verbatim can make tests brittle.

Define the contract clearly:

- If HTML output is fixed by the template, full comparison can work.
- If you only need to guarantee the logo reference and key notice exist, assert those essential elements.
- If full HTML semantics must be verified, use a proper HTML parser at the rendering test layer rather than crowding the MIME tree integration test.

### Can We Check Text Content Only and Skip the MIME Tree?

Not if you need to support diverse email clients. Two text parts sitting directly under **multipart/mixed** like two independent attachments behave differently from **multipart/alternative**. Tests should verify **both content and structural relationships**.

## 18. Verifying Charset and Unicode Subjects

A Vietnamese email may contain:

~~~text
Subject: Hóa đơn ORD-123 — đã thanh toán
Body:    Đơn hàng đã được thanh toán.
~~~

When built with **MimeMessageHelper(..., "UTF-8")**, you can assert:

~~~java
assertEquals(
        "Hóa đơn ORD-123 — đã thanh toán",
        actual.getSubject()
);

String plainContent =
        (String) plainNode.part().getContent();

assertTrue(
        plainContent.contains("đã được thanh toán")
);
~~~

**MimeMessage.getSubject()** returns the decoded value. Never assert that the raw `Subject` header literally equals a specific **=?UTF-8?B?...?=** string, because encoded-word representations can vary while remaining valid.

If you want to inspect the charset parameter:

~~~java
import jakarta.mail.internet.ContentType;

ContentType contentType = new ContentType(
        plainNode.part().getContentType()
);

assertTrue(
        "UTF-8".equalsIgnoreCase(
                contentType.getParameter("charset")
        )
);
~~~

If charsets can vary by policy while content still decodes properly, avoid pinning a specific charset solely because of library defaults. However, when the application **guarantees UTF-8**, asserting the parameter is appropriate.

### Content-Transfer-Encoding

Text parts may be encoded using:

- **quoted-printable**
- **base64**
- **7bit / 8bit** depending on conditions and configuration

Those are wire transport encodings, not what the reader sees. Unit/integration tests checking email semantics should use **getContent()** or **getInputStream()** to read **decoded data**, rather than comparing wire-format strings with specific line breaks or encodings.

## 19. Verifying Inline Images and Content-ID

HTML example:

~~~html
<img src="cid:brand-logo" alt="Store logo">
~~~

For the image to display via CID, the MIME tree must contain a part with:

- An appropriate Content-Type, such as **image/png**.
- **Content-ID: <brand-logo>** or an equivalent representation understood by MIME parsers.
- Proper placement relative to HTML content, typically inside the same **multipart/related** group.
- Readable image payload.

Example finding the part:

~~~java
MimeNodes.Node logo = related
        .first("image/png")
        .orElseThrow(() -> new AssertionError(
                "Missing image/png in related"
        ));

String[] cidHeaders =
        logo.part().getHeader("Content-ID");

assertNotNull(cidHeaders);
assertEquals(1, cidHeaders.length);
assertEquals(
        "<brand-logo>",
        cidHeaders[0].trim()
);
~~~

This example assumes the application sets Content-ID to **brand-logo**. Many MIME clients and libraries wrap Content-ID headers in angle brackets **<...>**, whereas HTML references **cid:brand-logo** without brackets.

To prevent tests from failing on whitespace or bracket formatting, add a normalization helper:

~~~java
public static String normalizeContentId(String header) {
    String cid = header.trim();
    if (cid.startsWith("<") && cid.endsWith(">")) {
        cid = cid.substring(1, cid.length() - 1);
    }
    return cid;
}
~~~

Then:

~~~java
assertEquals(
        "brand-logo",
        normalizeContentId(cidHeaders[0])
);
~~~

**Do not ignore genuine Content-ID mismatches:** tests must catch cases where HTML references **cid:brand-logo** while the part carries **other-logo**.

### Checking Image Disposition

~~~java
String disposition = logo.part().getDisposition();

assertTrue(
        disposition == null
        || disposition.equalsIgnoreCase(Part.INLINE)
);
~~~

In MIME, an inline resource may have **Content-Disposition: inline** or omit an explicit disposition, depending on the producer/transport. When targeting CID-referenced images, check **Content-ID, MIME type, and related placement** rather than forcing a single disposition string across all implementations.

However, if your application contract **mandates Content-Disposition: inline**, tighten the assertion and test how your helper/provider builds the message in your environment.

## 20. Verifying Decoded Inline Data

Checking metadata does not prove the image bytes were actually transmitted. You can compare bytes:

~~~java
import java.io.InputStream;
import java.util.Arrays;
import org.springframework.core.io.ClassPathResource;

byte[] expectedLogo;
try (InputStream input = new ClassPathResource(
        "mail/logo.png"
).getInputStream()) {
    expectedLogo = input.readAllBytes();
}

byte[] actualLogo;
try (InputStream input = logo.part().getInputStream()) {
    actualLogo = input.readAllBytes();
}

assertArrayEquals(expectedLogo, actualLogo);
~~~

**Part.getInputStream()** exposes part contents through the JavaMail API; normally Content-Transfer-Encoding is handled by the DataHandler. Thus tests compare decoded bytes rather than raw base64 strings whose line wrapping may vary.

Use small fixtures. If an image or attachment is large, reading the entire payload into memory just for assertions may be unsuitable; instead verify a digest and size limit.

## 21. Verifying Attachments on the mixed Branch

An independent attachment typically has:

~~~text
Content-Type: application/pdf; name="guide.pdf"
Content-Disposition: attachment; filename="guide.pdf"
Content-Transfer-Encoding: base64
~~~

In the example tree, the PDF must sit **outside the related branch holding HTML/inline images**, directly under **multipart/mixed**.

You can locate the PDF among descendants of root:

~~~java
MimeNodes.Node pdf = root
        .first("application/pdf")
        .orElseThrow(() -> new AssertionError(
                "Missing application/pdf attachment"
        ));

assertEquals(
        Part.ATTACHMENT,
        pdf.part().getDisposition()
);
assertEquals(
        "guide.pdf",
        pdf.part().getFileName()
);
~~~

To verify placement when structure is governed by **MIXED_RELATED**:

~~~java
assertFalse(
        related.first("application/pdf").isPresent(),
        "PDF attachment should not be inside the related branch"
);

assertTrue(
        root.directChildren("application/pdf").size() == 1,
        "PDF must be a direct part under mixed"
);
~~~

Using the right attachment filename and disposition matters to the recipient experience. If the application names attachments dynamically from business data, tests should compare against the expected event-driven filename rather than asserting "some PDF exists".

### Verifying Decoded Bytes of Attachments

~~~java
byte[] expectedPdf;
try (InputStream input = new ClassPathResource(
        "mail/guide.pdf"
).getInputStream()) {
    expectedPdf = input.readAllBytes();
}

byte[] actualPdf;
try (InputStream input = pdf.part().getInputStream()) {
    actualPdf = input.readAllBytes();
}

assertArrayEquals(expectedPdf, actualPdf);
~~~

This result confirms attachment data survives MIME encoding and the test SMTP transport within test scope. It does not guarantee every recipient's email client can open the file, yet catches broken data sources, single-use streams, or truncated attachments.

## 22. Asserting No Part Is Placed in the Wrong Branch

A MIME tree can contain every expected media type while still placing them in the wrong branches. For instance, HTML and the logo might be separated, or the PDF might land inside `related`:

~~~text
Wrong target:

multipart/mixed
|
+-- text/html
+-- multipart/related
|    +-- image/png
|
+-- application/pdf
~~~

Assertions that only count **text/html = 1**, **image/png = 1**, and **application/pdf = 1** would all pass. Yet the relationship between HTML and logo is broken.

With **MimeNodes.Node**, you can assert:

~~~java
assertTrue(
        related.first("text/html").isPresent(),
        "HTML must be inside related"
);

assertTrue(
        related.first("image/png").isPresent(),
        "Logo must be in the same related branch as HTML"
);

assertFalse(
        related.first("application/pdf").isPresent(),
        "Independent PDF does not belong inside related content"
);
~~~

If you want to verify there are no extra parts:

~~~java
long htmlCount = root.all().stream()
        .filter(node -> {
            try {
                return node.isType("text/html");
            } catch (jakarta.mail.MessagingException ex) {
                throw new IllegalStateException(ex);
            }
        })
        .count();

assertEquals(1, htmlCount);
~~~

Only assert exact counts when part of the contract. If a valid email includes an extra HTML part inside an attached **message/rfc822**, a rule demanding "exactly one HTML across the whole tree" will break. Define the exact **branch scope** under test.

## 23. Verifying Multiple Inline Resources

An email may use a logo, status icon, and banner:

~~~html
<img src="cid:brand-logo" alt="Logo">
<img src="cid:status-icon" alt="Status">
<img src="cid:offer-banner" alt="Info">
~~~

In Spring code:

~~~java
helper.setText(plainText, htmlText);

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

helper.addInline(
        "status-icon",
        new ClassPathResource("mail/status.png"),
        "image/png"
);

helper.addInline(
        "offer-banner",
        new ClassPathResource("mail/banner.png"),
        "image/png"
);
~~~

Tests should ensure:

- HTML references every required CID.
- The MIME tree contains a matching part for each CID.
- No two parts share the same **Content-ID** within a message when unique identifiers are required.
- Each resource has the expected MIME type and decoded bytes.
- Referenced parts reside in the appropriate `related` group.

### Collecting Content-IDs

Example test helper:

~~~java
import jakarta.mail.Part;
import java.util.ArrayList;
import java.util.List;

public static List<String> contentIds(
        MimeNodes.Node related
) throws Exception {
    List<String> ids = new ArrayList<>();

    for (MimeNodes.Node node : related.all()) {
        String[] headers = node.part().getHeader("Content-ID");

        if (headers != null) {
            for (String header : headers) {
                ids.add(normalizeContentId(header));
            }
        }
    }
    return List.copyOf(ids);
}
~~~

Then:

~~~java
assertEquals(
        Set.of("brand-logo", "status-icon", "offer-banner"),
        Set.copyOf(contentIds(related))
);

assertEquals(
        3,
        contentIds(related).size(),
        "Content-ID must not be duplicated"
);
~~~

The **normalizeContentId(...)** helper was defined in the previous section. Checking both the set and the count catches both missing CIDs and duplicate CIDs.

**Note:** Content-ID syntax has its own rules, where identifiers can resemble a Message-ID. Tests should not arbitrarily lowercase or strip characters; compare the exact identifier chosen by the application and parse HTML **cid:** URLs according to proper rules.

## 24. MIME Trees for HTML-Only or Plain-Text-Only Emails

Not every email needs all four part types. Valid structure depends on content.

### Plain-Text-Only Email

~~~text
MimeMessage
Content-Type: text/plain; charset=UTF-8
~~~

If the code writes:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        false,
        "UTF-8"
);

helper.setText("Simple notification.", false);
~~~

Tests can assert:

~~~java
assertTrue(received.isMimeType("text/plain"));
assertEquals(
        "Simple notification.",
        received.getContent()
);
~~~

### HTML-Only Email

If the service calls **setText(html, true)** without providing a plain-text alternative, the MIME tree may simply contain **text/html**. If the contract requires a plain-text fallback, tests must catch the missing **multipart/alternative** or **text/plain** part.

### Plain Text + HTML Email

When no inline resources or attachments exist, the service can use **multipart/alternative** directly without `mixed`/`related`:

~~~text
MimeMessage
└── multipart/alternative
    ├── text/plain
    └── text/html
~~~

Do not enforce a rigid assertion that "root must always be multipart/mixed" for every email type. Pick expected structures based on **actual content and the multipart mode** used by the service.

## 25. Impact of Multipart Mode in MimeMessageHelper

Spring **MimeMessageHelper** offers several multipart modes. Each mode governs how the tree is built.

| Mode | Intent | What to Observe |
|---|---|---|
| **MULTIPART_MODE_NO** | Simple message without multipart | Typically a single text body; unsuitable for multiple MIME resources |
| **MULTIPART_MODE_MIXED** | Groups parts under mixed | Parts may sit together under mixed; inline compatibility depends on clients |
| **MULTIPART_MODE_RELATED** | Groups display-related parts | HTML and inline resources sit under related |
| **MULTIPART_MODE_MIXED_RELATED** | Combines attachments and inline resources | Outermost mixed, related for content/inline resources |

The default mode when using the boolean **multipart=true** constructor in modern Spring Mail is typically **MIXED_RELATED**. To keep structure-focused integration tests clear and unambiguous, the main example selects the mode via constant:

~~~java
new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

### Why Not Choose Mode Based Solely on Attachment Count?

Having an attachment does not guarantee inline resources render properly across all email clients. If the application must display a logo alongside HTML and attach a separate PDF, **MIXED_RELATED** is an appropriate structure to test. Different clients vary in support, so test on target clients when rendering fidelity is critical.

### Structural Tests to Catch Accidental Changes

When a developer changes:

~~~java
MULTIPART_MODE_MIXED_RELATED
~~~

to:

~~~java
MULTIPART_MODE_MIXED
~~~

tests checking the **related -> alternative + inline** relationship will fail. That is a meaningful structural change, not a random formatting difference. If the change is intentional, redefine the MIME contract the application aims to support.

## 26. Bcc and MIME Data Received by the Test SMTP Server

Bcc has a crucial property: **blind-carbon-copy addresses are used in the SMTP envelope, yet must not appear in headers of the MIME DATA delivered to recipients**.

Suppose the application prepares:

~~~java
helper.setTo("customer@localhost");
helper.setBcc("audit@localhost");
~~~

The SMTP protocol exchange may look like:

~~~smtp
MAIL FROM:<notices@example.com>
RCPT TO:<customer@localhost>
RCPT TO:<audit@localhost>
DATA
From: notices@example.com
To: customer@localhost
Subject: Hóa đơn ORD-123
...
~~~

If the transport handles Bcc properly, headers in `DATA` sent to recipients never expose **audit@localhost**. However, **the pre-send MimeMessage** may still hold the Bcc field so the transport knows the recipient list.

Thus, maintain two verification layers:

1. **Pre-send unit test:** verify **getRecipients(Message.RecipientType.BCC)** returns the intended address and Bcc was not mistakenly placed in To/Cc.
2. **Post-SMTP-submission integration test:** the server captures **the actual MIME DATA received** and, if supported by the tool, **envelope recipients**. Confirm Bcc was an envelope recipient yet absent from delivered headers.

An assertion on the message received by GreenMail might be:

~~~java
assertNull(
        actual.getHeader("Bcc"),
        "MIME DATA must not expose the Bcc header"
);
~~~

**Note on test servers:** not every message-retrieval API reflects each final delivered copy identically, and some servers copy/rebuild messages per mailbox. When verifying Bcc privacy, ensure the API returns **the DATA transmitted by the transport**, not the original pre-send object or a copy augmented with test-server metadata.

### Why Not Check Only getAllRecipients()?

**MimeMessage.getAllRecipients()** reads recipient headers represented in the message. It does not directly inspect every **RCPT TO** command sent over the socket. If a test must prove Bcc at the envelope level, use an SMTP test server that records envelope commands or an equivalent capture API.

If the test server does not expose envelope data, you can still assert that the Bcc header is absent, while documenting the verification limit clearly: **Bcc inclusion in SMTP RCPT TO is not directly verified**.

## 27. Testing Attachment Filenames with Unicode

Attachment filenames can be in Vietnamese:

~~~text
Hóa đơn tháng 11.pdf
Báo cáo thanh toán.pdf
~~~

When building the message:

~~~java
helper.addAttachment(
        "Hóa đơn tháng 11.pdf",
        new ClassPathResource("mail/guide.pdf"),
        "application/pdf"
);
~~~

Tests should verify the **decoded** filename via the JavaMail API:

~~~java
String receivedName = pdf.part().getFileName();

assertEquals(
        "Hóa đơn tháng 11.pdf",
        receivedName
);
~~~

MIME headers can encode filenames using parameter encoding per library and configuration. Do not assert that raw headers literally hold unencoded Unicode strings. If an API returns an encoded name undecoded under current settings, handle it with **MimeUtility** or appropriate Jakarta Mail APIs for your version.

### Filenames Should Not Contain User-Supplied Paths

Email attachment filenames should be **display names**, without filesystem paths such as:

~~~text
C:\Users\someone\private\report.pdf
/home/service/secrets/report.pdf
~~~

When deriving filenames from input or paths, sanitize and allow only permitted characters. Integration tests can verify filenames contain no internal paths or control characters. Never put production files or sensitive data into test fixtures.

## 28. Do Not Depend on Random MIME Boundaries, Message-IDs, or Dates

A MIME message may serialize to:

~~~text
Content-Type: multipart/mixed;
  boundary="----=_Part_23_6984725.1762920000000"
Message-ID: <284923.12.1762920000000@example.com>
Date: Thu, 12 Nov 2026 15:30:00 +0700
~~~

These values can change across message creations:

- **Boundary** strings are typically generated to separate MIME parts.
- **Message-ID** may be generated or modified during `saveChanges`/transport.
- **Date** depends on execution time.
- **Content-Transfer-Encoding** may vary by charset and payload.
- **Header ordering** and folding may vary.

When targeting the MIME tree, avoid doing:

~~~java
assertEquals(expectedRawEml, serializedEml);
~~~

unless the application genuinely needs byte-for-byte serialization testing and controls every variable field.

Instead:

- Use **isMimeType(...)** to check part types.
- Traverse containers to verify relationships.
- Read decoded content and compare meaningful values.
- Check Content-ID after normalizing angle brackets.
- Compare attachment filenames and decoded bytes.
- Check `Subject`/`From`/`To` headers via Jakarta Mail APIs.

### When Should You Inspect Raw MIME?

Occasionally applications have strict requirements around encoded-words, `Content-Transfer-Encoding`, or compatibility with a specific mail system. In those cases, inspect raw MIME or **EML** in dedicated tests so the entire integration suite does not depend on unrelated volatile details.

## 29. Verifying Exact Counts of Expected Parts

In structural tests, you can apply rules such as:

~~~text
Expected:
  1 multipart/mixed root
  1 multipart/related under mixed
  1 multipart/alternative under related
  1 text/plain under alternative
  1 text/html under alternative
  1 image/png with Content-ID brand-logo under related
  1 application/pdf attachment under mixed
~~~

This is stronger than checking a few substrings:

~~~java
assertEquals(
        1,
        related.directChildren("image/png").size()
);

assertEquals(
        1,
        root.directChildren("application/pdf").size()
);

assertEquals(
        1,
        alternative.directChildren("text/plain").size()
);

assertEquals(
        1,
        alternative.directChildren("text/html").size()
);
~~~

Direct-child assertions suit the **explicit structure defined in the example**. Another library or template might introduce an extra valid multipart layer, so before writing assertions decide whether this is an **intentionally chosen application contract** or an implementation detail.

### Checking for Unexpected Attachments

If an email may attach only one PDF, a test can count all parts with disposition **attachment** and assert the count is one. Watch for null dispositions on inline resources; never treat every non-text part as an attachment.

~~~java
long attachments = 0;

for (MimeNodes.Node node : root.all()) {
    String disposition = node.part().getDisposition();
    if (disposition != null
            && disposition.equalsIgnoreCase(Part.ATTACHMENT)) {
        attachments++;
    }
}

assertEquals(1, attachments);
~~~

This catches a logo accidentally added via **addAttachment(...)** even while the valid PDF remains present.

## 30. Failure Scenarios Worth Integration Testing

For tests to catch real defects, include variant cases beyond the happy path:

| Scenario | What the Test Must Catch |
|---|---|
| Calling **setText(html, true)** without plain text | Missing alternative required by policy |
| Using **addAttachment** for logo | Logo lacks proper inline/CID relationship |
| HTML references wrong CID | Content-ID and `src="cid:..."` mismatch |
| Missing image resource on classpath | Unable to build/send expected message |
| Single-use attachment stream exhausted | Decoded bytes empty, corrupted, or mismatching fixture |
| Using **MULTIPART_MODE_MIXED** instead of **MIXED_RELATED** | MIME tree relationships violate contract |
| Missing charset configuration | Unicode subject or body fails expectations |
| Wrong filename | MIME filename differs from intended display name |
| Bcc accidentally placed in Cc | Blind recipient exposed in public headers |
| Extra unexpected attachment | Attachment part count exceeds contract |
| Sending multiple notifications to unreset test server | Test reads stale mail, miscounts, or grabs wrong message |

There is no need to cram every error into one giant integration test. Split key cases into small tests, each verifying a clearly named invariant.

### Example: Detecting a Missing CID

Suppose the HTML is:

~~~html
<img src="cid:brand-logo">
~~~

yet the application adds:

~~~java
helper.addInline(
        "other-logo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

A test that only checks an **image/png** exists will still pass. A proper test compares **cid:brand-logo** against the received Content-ID and fails on mismatch.

### Example: Detecting Wrong Multipart Grouping

If a message has plain text, HTML, and PDF without **multipart/alternative**, some email clients may display the plain text as an independent part instead of selecting HTML. Structural tests catch this before release.

## 31. Distinguishing MIME Construction Failures from SMTP Transport Failures

An integration test can fail before GreenMail receives the message. In that case, you cannot conclude the MIME tree is wrong.

~~~text
Service
   |
   +-- Message construction error
   |     -> MessagingException
   |     -> missing fixture file
   |     -> missing content
   |
   v
JavaMailSenderImpl
   |
   +-- SMTP connection error
   |     -> DNS / refused / timeout
   |     -> wrong test host or port
   |
   v
GreenMail
   |
   +-- Message received
   |     -> MIME tree assertions
   |
   v
Test finishes
~~~

Diagnose failures by layer:

- **Missing fixture file:** fix test resources and paths.
- **MessagingException when helper sets content:** check message construction.
- **MailSendException from JavaMailSender:** check server startup, host, port, timeouts, or test SMTP policies.
- **waitForIncomingEmail timeout:** check actual send call, recipient, and server status.
- **MIME tree assertion failure after receipt:** check multipart mode, `addInline`/`setText` ordering, Content-Type, or data sources.

Never increase SMTP timeouts to fix an attachment placed in the wrong MIME branch. Conversely, never alter MIME tree expectations because the test server failed to start.

## 32. Inspecting Output in a Spring Boot Integration Test

In the earlier example, the test created **JavaMailSenderImpl** and the service manually. That suffices to verify Spring Mail transport against a local SMTP server without booting the whole application.

If the goal is testing **Spring Boot auto-configuration** and template/service wiring, use **@SpringBootTest** with mail properties pointing to GreenMail:

~~~text
@SpringBootTest
      |
      +-- Spring creates JavaMailSender from application-test.yml
      |
      +-- NotificationService uses real bean
      |
      +-- GreenMail server running on localhost
      |
      +-- Test reads and analyzes MIME tree
~~~

In that scenario, manage lifecycle ordering: GreenMail must have its listener ready before services start sending. If using a dynamic port, **spring.mail.port** must be supplied at the right moment when creating the `ApplicationContext`.

Common options:

- Use a JUnit extension managing GreenMail before tests and supplying properties.
- Use dynamic properties in the Spring test context once test server configuration is ready.
- Use Testcontainers/an SMTP capture server with mapped ports and dynamic test configuration.
- For small examples, instantiate the sender manually as before to avoid `ApplicationContext` overhead.

Never hard-code production credentials or let **application-test.yml** accidentally point to real SMTP. An integration test running in CI must execute independently of the Internet.

## 33. Using a Containerized SMTP Capture Server

Replacing GreenMail with a containerized SMTP capture server is also a solid choice if the project already uses Testcontainers.

Architecture example:

~~~text
JUnit/Testcontainers
      |
      +-- Start Mailpit container
      |      |
      |      +-- SMTP port (mapped)
      |      +-- Message inspection API
      |
      +-- Set spring.mail.host/port for test
      |
      +-- Call notification service
      |
      +-- Poll message capture API with bounded timeout
      |
      +-- Retrieve raw MIME/EML or parsed message
      |
      +-- Parse with jakarta.mail.internet.MimeMessage
      |
      +-- Assert MIME tree
~~~

When downloading raw EML from the capture server's API, you can construct a **MimeMessage** with Jakarta Mail:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.InputStream;
import java.util.Properties;

Session session = Session.getInstance(new Properties());

try (InputStream emlInputStream = /* stream from test server */) {
    MimeMessage parsed = new MimeMessage(
            session,
            emlInputStream
    );

    MimeNodes.Node root = MimeNodes.read(parsed);
    assertTrue(root.isType("multipart/mixed"));
}
~~~

This is a skeleton; how you call the API to fetch raw EML depends on the version and running mode of Mailpit/MailHog. Do not assume every API returns messages in the same JSON schema or supports identical endpoints. When tests only need Java `MimeMessage` directly, GreenMail often requires fewer moving parts.

### Why Is Parsing Raw EML Still Useful?

Tests do not depend on how the SMTP capture server models MIME trees in JSON. The application can use **Jakarta Mail** to interpret the same MIME representation it sent and assert invariants.

However, when verifying compatibility with mail clients that do not use Jakarta Mail, add rendering or client-specific tests at another layer. A consistent parser does not prove every client renders identically.

## 34. Isolating Tests When Running in Parallel in CI

Some integration test failures stem from the execution environment rather than email structure:

- Two tests share a fixed SMTP port.
- The previous test's server has not stopped completely.
- A new test reads stale messages from the inbox.
- Multiple tests send to one test mailbox and inspect **getReceivedMessages()[0]**.
- One slow test causes another test to time out.

### Isolation Principles

1. Give each test or test group a clear **SMTP server lifecycle**.
2. When running in parallel, use **dynamically allocated ports** or isolated server/container instances.
3. Use **separate mailboxes/recipients** for tests that might overlap.
4. Never use an unreset shared server and assert total system-wide message count.
5. Use bounded waits instead of fixed-duration sleeps.
6. Always clean up resources in **@AfterEach** or extension lifecycles.

Wait example:

~~~java
assertTrue(
        greenMail.waitForIncomingEmail(5000, 1),
        "Message did not arrive at SMTP test server within test limits"
);
~~~

Better than:

~~~java
Thread.sleep(5000);
~~~

because the wait method can return as soon as enough messages arrive, whereas `sleep` always waits the full duration and does not express the success condition.

For asynchronous or outbox-based mail systems, you may need to poll both **submitted** status and the SMTP inbox within a finite timeout. Tests should distinguish:

- Worker has not picked up the notification yet.
- Worker is currently processing.
- SMTP server has not received it yet.
- SMTP server received it, yet MIME assertions failed.

Do not make a MIME tree test depend on full production scheduler speeds when testing the async pipeline is not the goal.

## 35. Security and Limits When Analyzing MIME from a Test Server

Emails can contain private data. Even in integration tests, observe:

- Use **test addresses**; never send to real recipients.
- Never use production OTPs, recovery tokens, card numbers, or real invoices as fixtures.
- Never print full raw EML or decoded attachments into CI logs.
- Protect log artifacts if tests fail.
- Never fetch remote links or images from HTML during MIME parsing.
- When parsing untrusted MIME, limit depth, total parts, bytes, and processing time.
- Never automatically open or execute attachments extracted from emails.
- Never save an attachment filename as a filesystem path without sanitization.

### A MIME Parser Is Not a Browser

Reading **text/html** via **Part.getContent()** does not require rendering HTML or fetching external resources. Tests can inspect HTML strings and CID references without touching the Internet.

If using an HTML parser to extract **src="cid:..."** values, isolate them from remote URLs like **https://...**. Never auto-fetch every URL just to "verify images", as that turns an offline test into external network traffic and introduces SSRF risk if HTML comes from untrusted sources.

### Do Not Use Fixtures Containing PII

An example Subject:

~~~text
Hóa đơn ORD-123 — đã thanh toán
~~~

is plenty to test Unicode and mapping. There is no need to use real customer names, addresses, or emails.

## 36. Writing Negative Test Cases for the MIME Tree

A happy-path test shows **the current structure is valid**. Negative cases prove assertions can actually catch defects.

### Case 1: Logo Added as an Attachment

Instead of:

~~~java
helper.addInline(
        "brand-logo",
        logoResource,
        "image/png"
);
~~~

the code is changed to:

~~~java
helper.addAttachment(
        "logo.png",
        logoResource,
        "image/png"
);
~~~

The test must fail because:

- The `related` branch lacks CID **brand-logo**, or
- Attachment count exceeds expectations, or
- The image lacks the contractually required relationship with HTML.

### Case 2: Missing Plain-Text Alternative

If the code calls:

~~~java
helper.setText(htmlText, true);
~~~

instead of:

~~~java
helper.setText(plainText, htmlText);
~~~

and the contract requires both plain text and HTML, assertions on **multipart/alternative** or **text/plain** must fail.

### Case 3: Wrong Content-ID

If HTML references **cid:brand-logo** while the MIME part has Content-ID **other-logo**, the test must detect the mismatch even if the PNG exists with valid bytes.

### Case 4: Attachment Missing Expected Data

If the source resource is empty or truncated, assertions comparing decoded bytes must fail.

### Case 5: Wrong MIME Branch

If a service switches modes or builds a MIME tree manually so the PDF lands inside `related`, parent-child relationship assertions must fail.

Negative cases should use dedicated test fixtures rather than intentionally breaking production files just to induce failures. You can build a test composer parameterized by mode or construct dedicated test message objects.

## 37. Recommended Invariants by Email Type

Instead of forcing every email into a single MIME tree, define distinct contracts:

| Email Type | Key Invariants |
|---|---|
| Simple plain text | `text/plain`, proper charset, accurate content |
| Plain text + HTML | `multipart/alternative` containing `text/plain` and `text/html` |
| HTML with CID logo | HTML and image/Content-ID under `related`, matching CID references |
| HTML + attachment | `mixed` holding content and independent attachment |
| HTML + inline + attachment | `mixed` -> `related` -> `alternative`, inline image under `related`, attachment under `mixed` |
| Multi-attachment email | Accurate counts, filenames, MIME types, dispositions, and bytes per file |
| Multi-recipient and Bcc email | Accurate `To`/`Cc` headers; Bcc absent from `DATA`, envelope recipients verified if supported |

When organizing the test suite, name tests to express the invariant being proven:

~~~text
shouldSendPlainAndHtmlAsAlternatives()
shouldKeepInlineLogoRelatedToHtml()
shouldAttachPdfOutsideRelatedContent()
shouldPreserveUnicodeSubjectAndBody()
shouldNotExposeBccInCapturedMimeData()
shouldPreserveDecodedAttachmentBytes()
~~~

Behavior-oriented test names make CI reports far easier to read than implementation names like **testHelper1** or **testMime2**.

## 38. Common Mistakes When Testing MIME Trees

| Mistake | Why It Is Inadequate | Better Direction |
|---|---|---|
| Only verifying **mailSender.send(any())** | Does not inspect SMTP-received payload | Use a test server and read MIME |
| Mocking the entire `MimeMessage` | Does not reflect real serialization | Use real `MimeMessage` with transport tests |
| Checking only attachment count | Cannot tell if inline/CID is right | Check placement, disposition, Content-ID |
| Comparing raw EML byte-for-byte | Boundary/Message-ID/Date can vary | Assert semantic tree |
| Comparing full `Content-Type` string | Contains boundary, charset, and parameters | Use `isMimeType` and `ContentType` parser |
| Searching `text/plain` and `text/html` anywhere in tree | Multipart relationships may still be wrong | Verify they reside inside `alternative` |
| Asserting only that an `image/png` exists | HTML may reference a different CID | Match HTML `cid` against `Content-ID` |
| Treating pre-send object as SMTP capture | Does not prove transport sent it | Read from real test server |
| Asserting Bcc null on pre-send object | Fails to verify Bcc recipient selection | Separate pre-send and SMTP DATA tests |
| Reading Bcc from headers to infer `RCPT TO` | Headers differ from SMTP envelope | Use envelope capture when needed |
| Comparing raw base64 strings | Folding and encoding can vary | Compare decoded bytes |
| Using large files or real customer data | Heavy tests and data risks | Use small, synthetic fixtures |
| Using production SMTP in CI | External side effects and network coupling | Local/container sandbox server |
| Using a fixed port across parallel tests | Port collisions and flakiness | Dynamic ports or isolated instances |
| Parsing HTML and fetching all URLs | Network calls and SSRF risk | Check structure and CIDs offline only |
| Unbounded MIME traversal | Deep trees or huge part counts exhaust resources | Cap depth, nodes, and bytes |

## 39. Runbook When a MIME Tree Assertion Fails

When a test fails, investigate in order:

1. **Did the SMTP server receive the message?** If not, focus on setup, host, port, and exceptions.
2. **Is it the right message?** Check Subject/recipient and avoid inbox contamination from other tests.
3. **What is the root Content-Type?** Plain text, alternative, related, or mixed?
4. **Are multipart branches right?** Inspect parent-child hierarchy, not just a flat list.
5. **Are plain text and HTML inside alternative?** Compare decoded content.
6. **Which CIDs does HTML reference?** Compare against inline part Content-IDs.
7. **Where do inline resources live?** Check `related`, Content-Type, and disposition.
8. **Where do attachments live?** Check `mixed`, filename, disposition, and decoded bytes.
9. **Is charset right?** Use decoded `getSubject`/`getContent`, and check `Content-Type` if needed.
10. **Is the test depending on volatile details?** Boundaries, encoding, Message-ID, header folding, or unspecified ordering.
11. **Did the test server alter the message?** Some proxies/ESPs rewrite headers or structure.
12. **Was the change intentional?** If the composer changed multipart mode, update contract tests with explanation rather than deleting failing assertions.

### Example Failure Output

~~~text
Expected:
  related -> alternative -> text/plain + text/html

Actual:
  mixed -> text/html + image/png + application/pdf
~~~

When seeing this discrepancy, inspect **multipart mode** and how the composer calls **setText/addInline/addAttachment**. Simply receiving SMTP 250 does not mean the structure is valid for email clients.

## 40. Summary

**Verifying the MIME tree on a test server** is a vital integration test for emails containing HTML, plain-text alternatives, inline images, and attachments in Spring Framework Mail.

Core workflow:

1. Build emails using real **JavaMailSenderImpl** and **MimeMessageHelper** with predictable content/fixtures.
2. Send through a **test SMTP server** such as GreenMail or an isolated SMTP capture server, never production SMTP.
3. Wait for receipt and retrieve the received **MimeMessage or raw EML**.
4. Traverse **Part / Multipart / BodyPart** to model the MIME tree.
5. Assert **multipart/mixed -> multipart/related -> multipart/alternative** relationships when that is the contract for emails with attachments and inline resources.
6. Verify **Content-Type**, **Content-ID**, **Content-Disposition**, filenames, Subject/charset, and decoded contents/bytes.
7. Verify Bcc at the right layer: recipient selection before send, and privacy via SMTP DATA/envelope when supported by the tool.
8. Avoid depending on volatile boundaries, encoded-words, Message-IDs, or non-contractual header order.
9. Isolate SMTP servers, mailboxes, and fixtures so tests run stably in CI.

**The goal is not to test whether Jakarta Mail can generate some arbitrary MIME string, but to prove that emails arrive at the test server with the exact content parts and MIME relationships email clients need to render them properly.** This layer complements service unit tests prior to production rollout and target-client rendering checks.


