# Testing MimeMessageHelper with Multipart

In Spring Framework Mail, `MimeMessageHelper` helps build emails with plain text, HTML, inline images, and file attachments. Calls like `setText(plainText, htmlText)`, `addInline(...)`, or `addAttachment(...)` look simple, yet the result is a multi-part MIME structure where each part has its own Content-Type, charset, disposition, Content-ID, and encoding. If you only check that the method does not throw an exception, the email may still miss HTML, lose CID images, or lack the expected attachment.

**Unit testing `MimeMessageHelper` with multipart** means testing the content and structure of a `MimeMessage` right inside the JVM, without needing an SMTP server or network. This lesson builds tests using JUnit 5, Jakarta Mail, and Spring Mail; explains how to inspect MIME parts after construction, avoid assertions coupled to dynamic boundaries, verify attachment bytes, and distinguish unit tests from integration tests.

## 1. Components to understand

| Component | Role | Test point |
| --- | --- | --- |
| `JavaMailSender` | API to create and send messages | Can mock `createMimeMessage()` and `send(...)` |
| `MimeMessageHelper` | Builds headers, body, and MIME parts | Choose the appropriate multipart mode |
| `MimeMessage` | Message holding headers and content | Can be created in-memory via Jakarta Mail |
| `Multipart` | Container holding multiple `BodyPart` entries | May be nested across multiple levels |
| `Part` / `BodyPart` | A MIME part | MIME type, decoded content, disposition, filename |
| `InputStreamSource` | Supplies bytes for attachments/inline items | Resource should be re-readable when needed |
| `Content-ID` | Links inline images with `cid:` URIs | Value in HTML and header must match |
| `Content-Type` | Data type, charset, boundary | Parse instead of comparing raw strings |

A text-only email does not require `Multipart`; an email with HTML, images, and attachments may have several nested `Multipart` levels. Tests must reflect the expected structure for the chosen mode.

## 2. How do single-part and multipart differ?

### Single-part

```java
MimeMessage message = new MimeMessage(
        Session.getInstance(new Properties())
);

MimeMessageHelper helper =
        new MimeMessageHelper(message, "UTF-8");
helper.setText("Hello, this is a plain-text email.", false);
```

In this case, `message.getContent()` can be a `String`. Casting directly to `Multipart` will fail even though the message is valid.

### Multipart alternative

```java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(
        "Your order has been confirmed.",
        "<p>Your order <strong>has been confirmed</strong>.</p>"
);
```

The `setText(String plainText, String htmlText)` overload creates two representations for the same content, typically inside `multipart/alternative`. Mail clients can pick either the text or HTML version.

### Multipart with inline and attachment

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setText(plainText, htmlText);
helper.addInline(
        "logo",
        new ByteArrayResource(logoBytes),
        "image/png"
);
helper.addAttachment(
        "report.bin",
        new ByteArrayResource(fileBytes),
        "application/octet-stream"
);
```

Here, parts may be nested across `multipart/mixed`, `multipart/related`, and `multipart/alternative`. You cannot assume HTML is always `getBodyPart(0)` of the root.

## 3. Multipart modes of MimeMessageHelper

| Mode | Structure | Best suited for |
| --- | --- | --- |
| `MULTIPART_MODE_NO` | Non-multipart | Simple text |
| `MULTIPART_MODE_MIXED` | Root `multipart/mixed` | Combining multiple parts/attachments |
| `MULTIPART_MODE_RELATED` | Root `multipart/related` | Resources closely related to the body |
| `MULTIPART_MODE_MIXED_RELATED` | Root `multipart/mixed` containing a `multipart/related` branch | HTML with inline images and attachments |

The constructor `new MimeMessageHelper(message, true, "UTF-8")` uses Spring's default multipart mode. In structural tests, specifying the mode explicitly helps readers understand intent and reduces reliance on undocumented assumptions.

A common tree:

```text
MimeMessage
  |
  +-- multipart/mixed
        |
        +-- multipart/related
        |     |
        |     +-- multipart/alternative
        |     |     +-- text/plain; charset=UTF-8
        |     |     +-- text/html; charset=UTF-8
        |     |
        |     +-- image/png; Content-ID: <logo>
        |
        +-- application/octet-stream
              Content-Disposition: attachment
              filename=report.bin
```

The diagram is illustrative. Some details can vary by mode and library version; rather than hardcoding indices at every level, verify the existence of parts and meaningful MIME relationships.

## 4. Unit tests do not need a real SMTP server

```text
JUnit 5
   |
   v
Jakarta Mail Session (in-memory)
   |
   v
MimeMessage + MimeMessageHelper
   |
   v
Read back Part / Multipart / headers
   |
   v
JUnit assertions
```

`Session.getInstance(new Properties())` opens no network connection. `new MimeMessage(session)` creates the message in memory. Unit tests verify that data was **built properly**; they do not prove SMTP accepts the message, nor do they test TLS or Gmail/Outlook rendering.

Integration tests can send to GreenMail, Mailpit, or MailHog and inspect the message actually received by the test SMTP server. The two test types complement each other and do not replace one another.

## 5. Dependencies and namespaces

With Spring Boot 3.x/Spring Framework 6+, code typically uses `jakarta.mail`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Spring Boot manages compatible library versions. Older Spring versions may use `javax.mail`; never mix `javax.mail.*` and `jakarta.mail.*` imports in the same test.

JUnit 5 is included in the Spring Boot test starter; Mockito and AssertJ are also typically provided by starter-test. The examples below use standard JUnit assertions to minimize extra syntactic dependencies.

## 6. Create an in-memory MimeMessage

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;

static MimeMessage newMessage() {
    Session session = Session.getInstance(new Properties());
    return new MimeMessage(session);
}
```

No SMTP username/password or network is needed. If composer code depends on `JavaMailSender`, you can mock `createMimeMessage()` or use `JavaMailSenderImpl.createMimeMessage()` without calling `send`.

```java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
MimeMessage message = sender.createMimeMessage();
```

`createMimeMessage()` only creates the object; SMTP transport does not run in this step.

## 7. Write a utility to traverse the MIME tree

Parts can sit at multiple nesting depths, so write a recursive `Multipart` traversal utility instead of checking fixed positions.

```java
import jakarta.mail.MessagingException;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MimeTestParts {

    private MimeTestParts() {}

    public static List<Part> flatten(Part root)
            throws MessagingException, IOException {
        List<Part> result = new ArrayList<>();
        visit(root, result);
        return result;
    }

    private static void visit(Part part, List<Part> result)
            throws MessagingException, IOException {
        result.add(part);

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    visit(multipart.getBodyPart(i), result);
                }
            }
        }
    }

    public static boolean contains(
            List<Part> parts, String mimeType
    ) throws MessagingException {
        for (Part part : parts) {
            if (part.isMimeType(mimeType)) {
                return true;
            }
        }
        return false;
    }

    public static Part require(
            List<Part> parts, String mimeType
    ) throws MessagingException {
        for (Part part : parts) {
            if (part.isMimeType(mimeType)) {
                return part;
            }
        }
        throw new AssertionError("Missing MIME type: " + mimeType);
    }

    public static Part requireDisposition(
            List<Part> parts, String disposition
    ) throws MessagingException {
        for (Part part : parts) {
            if (disposition.equalsIgnoreCase(part.getDisposition())) {
                return part;
            }
        }
        throw new AssertionError(
                "Missing disposition: " + disposition);
    }
}
```

### Why use loops?

`Part.isMimeType(...)` and related APIs can throw checked `MessagingException`. Using loops avoids compilation friction with Java Stream `Predicate`, which does not declare checked exceptions.

This utility is intended only for small test-generated messages. When processing MIME received from untrusted sources, limit part count, depth, bytes, and parse time to prevent resource exhaustion.

## 8. Test that plain text and HTML coexist

```java
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;
import java.util.List;
import java.util.Properties;
import static org.junit.jupiter.api.Assertions.*;

class AlternativeMimeTest {

    @Test
    void containsPlainAndHtml() throws Exception {
        MimeMessage message =
                new MimeMessage(Session.getInstance(new Properties()));

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        String plain = "Xin chào, đơn hàng đã xác nhận.";
        String html = "<p>Xin chào, <strong>đơn hàng"
                + " đã xác nhận</strong>.</p>";

        helper.setFrom("notice@example.org");
        helper.setTo("customer@example.net");
        helper.setSubject("Xác nhận đơn hàng");
        helper.setText(plain, html);

        message.saveChanges();
        List<Part> parts = MimeTestParts.flatten(message);

        assertTrue(MimeTestParts.contains(
                parts, "multipart/alternative"));
        Part textPart = MimeTestParts.require(parts, "text/plain");
        Part htmlPart = MimeTestParts.require(parts, "text/html");

        assertEquals(plain, textPart.getContent());
        assertEquals(html, htmlPart.getContent());
        assertEquals("Xác nhận đơn hàng", message.getSubject());
    }
}
```

The test asserts content **decoded** by Jakarta Mail without relying on raw transfer encoding. The library may choose `quoted-printable` or `base64` depending on the data; both are valid as long as content reconstructs faithfully.

## 9. Test UTF-8 charset properly

Do not compare the entire `Content-Type` string verbatim:

```java
// Brittle: casing, quotes, and parameter order may change.
assertEquals("text/html; charset=UTF-8",
        htmlPart.getContentType());
```

Parse it instead:

```java
import jakarta.mail.internet.ContentType;
import java.util.Locale;

ContentType htmlType =
        new ContentType(htmlPart.getContentType());

assertEquals("text/html",
        htmlType.getBaseType().toLowerCase(Locale.ROOT));
assertEquals("utf-8",
        htmlType.getParameter("charset")
                .toLowerCase(Locale.ROOT));

ContentType plainType =
        new ContentType(textPart.getContentType());
assertEquals("utf-8",
        plainType.getParameter("charset")
                .toLowerCase(Locale.ROOT));
```

A test containing `"Xin chào, đơn hàng đã xác nhận."` catches character-corruption bugs far better than checking headers alone. A `Content-Type` header stating UTF-8 does not by itself prove the source data preserved Unicode.

## 10. Test parent-child relationships in alternative

If the requirement is that `text/plain` and `text/html` live together inside a `multipart/alternative`:

```java
Part alternativePart =
        MimeTestParts.require(parts, "multipart/alternative");

Multipart alternative =
        (Multipart) alternativePart.getContent();

assertEquals(2, alternative.getCount());
assertTrue(alternative.getBodyPart(0).isMimeType("text/plain"));
assertTrue(alternative.getBodyPart(1).isMimeType("text/html"));
```

At the `multipart/alternative` level, having plain before HTML is meaningful; do not apply these indices to the root `multipart/mixed` or `multipart/related`. Those containers may hold additional resources/attachments.

## 11. saveChanges() in tests

`MimeMessage.saveChanges()` finalizes headers and state required for serialization. Typically call it after finishing message construction and before inspecting:

```java
MimeMessage message = newMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText("Text", "<p>HTML</p>");
message.saveChanges();

List<Part> parts = MimeTestParts.flatten(message);
```

Notes:

- `saveChanges()` can generate or update `Message-ID` and related headers.
- MIME boundaries are typically auto-generated; do not hard-code boundary values.
- `saveChanges()` does not send the email and produces no SMTP result.
- If you need to check pre-serialization state, test it separately with a clear phase name.

To ensure the message can be serialized and parsed back, add a round-trip test calling `writeTo(...)` and then constructing a `MimeMessage` from an `InputStream`.

## 12. Test multipart with attachment and inline image

This is the most comprehensive scenario in the lesson: an email with plain text, HTML, an inline logo via `cid:`, and a binary attachment. We want to prove each part is built with the right structure and data.

### Prepare test data

A binary attachment can use a fixed byte array, avoiding filesystem dependencies:

```java
byte[] attachmentBytes = new byte[] {
        0, 1, 2, 3, 4, 42, 100, 127, (byte) 255
};
```

For an inline image, use a small PNG file in `src/test/resources/mail/pixel.png`. This is a test fixture containing no user data:

```java
byte[] logoBytes;
try (InputStream input = getClass().getResourceAsStream(
        "/mail/pixel.png")) {
    assertNotNull(input, "Missing test resource pixel.png");
    logoBytes = input.readAllBytes();
}
```

In MIME tests, compare the inline part's bytes against the fixture file. Whether the PNG actually renders across every mail client falls under a separate integration/visual test scope.

### Test the full structure

```java
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.io.InputStream;
import java.util.Arrays;
import java.util.List;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.*;

class MixedRelatedMimeTest {

    @Test
    void buildsInlineImageAndAttachment() throws Exception {
        MimeMessage message = new MimeMessage(
                Session.getInstance(new Properties()));

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        String plain = "View the report and attached logo.";
        String html = "<p>View the report:</p>"
                + "<img src=\"cid:logo\" alt=\"Logo\">";

        byte[] attachmentBytes = new byte[] {
                0, 1, 2, 3, 4, 42, 100, 127, (byte) 255
        };

        byte[] logoBytes;
        try (InputStream input = getClass().getResourceAsStream(
                "/mail/pixel.png")) {
            assertNotNull(input);
            logoBytes = input.readAllBytes();
        }

        helper.setFrom("sender@example.org");
        helper.setTo("recipient@example.net");
        helper.setSubject("MIME test report");
        helper.setText(plain, html);

        // Add inline after HTML has been set.
        helper.addInline(
                "logo",
                new ByteArrayResource(logoBytes),
                "image/png"
        );
        helper.addAttachment(
                "sample.bin",
                new ByteArrayResource(attachmentBytes),
                "application/octet-stream"
        );

        message.saveChanges();
        List<Part> parts = MimeTestParts.flatten(message);

        assertTrue(MimeTestParts.contains(parts, "multipart/mixed"));
        assertTrue(MimeTestParts.contains(parts, "multipart/related"));
        assertTrue(MimeTestParts.contains(
                parts, "multipart/alternative"));
        assertEquals(plain,
                MimeTestParts.require(parts, "text/plain").getContent());
        assertEquals(html,
                MimeTestParts.require(parts, "text/html").getContent());

        Part inline = MimeTestParts.require(parts, "image/png");
        assertEquals(Part.INLINE, inline.getDisposition());
        assertNotNull(inline.getHeader("Content-ID"));
        assertTrue(Arrays.stream(inline.getHeader("Content-ID"))
                .anyMatch(value -> value.contains("logo")));
        assertArrayEquals(logoBytes,
                inline.getInputStream().readAllBytes());

        Part attachment = MimeTestParts.requireDisposition(
                parts, Part.ATTACHMENT);

        assertTrue(attachment.isMimeType(
                "application/octet-stream"));
        assertEquals("sample.bin", attachment.getFileName());
        assertArrayEquals(attachmentBytes,
                attachment.getInputStream().readAllBytes());
    }
}
```

This test verifies that the **message object** is constructed properly, unrelated to SMTP. The fixture file `pixel.png` must exist in test resources. If the fixture is missing, the test fails clearly with an assertion rather than producing a confusing error when reading the file.

### Key assertions

| Assertion | What it proves |
| --- | --- |
| `multipart/mixed` exists | Message has a branch combining multiple content items |
| `multipart/related` exists | Structure exists for related content parts |
| `multipart/alternative` exists | Clients can choose text or HTML |
| Plain/HTML read via `getContent()` | Decoded content matches the model |
| `Part.INLINE` and `Content-ID` | Inline part is marked and identified properly |
| Attachment has disposition and filename | File is attached with basic name/type metadata |
| `assertArrayEquals` on `getInputStream()` | Attachment/inline bytes are unaltered in the MIME representation |

There is no need to assert the entire raw MIME as one long string, and especially no need to compare random boundaries.

## 13. Verify Content-ID matches HTML

When adding an inline image:

```java
helper.setText(
        "Text content",
        "<img src=\"cid:logo\" alt=\"Logo\">"
);
helper.addInline(
        "logo",
        new ByteArrayResource(logoBytes),
        "image/png"
);
```

The MIME part carries headers such as:

```text
Content-ID: <logo>
Content-Disposition: inline
Content-Type: image/png
```

In tests, you can check:

```java
Part htmlPart = MimeTestParts.require(parts, "text/html");
String htmlContent = (String) htmlPart.getContent();

Part inlinePart = MimeTestParts.require(parts, "image/png");
String[] cidHeaders = inlinePart.getHeader("Content-ID");

assertTrue(htmlContent.contains("cid:logo"));
assertNotNull(cidHeaders);
assertTrue(Arrays.stream(cidHeaders)
        .anyMatch(value -> value.equals("<logo>")));
```

The value `cid:logo` is the URI reference in HTML, whereas `Content-ID: <logo>` is the MIME part header. Do not pass `cid:` or `< >` into the `addInline` overload if your code expects the bare content ID.

For messages with multiple inline resources, build an expected ID set and verify every reference has a matching part; do not check only the total image count, since the right count could still miss a specific ID.

### Order of setText and addInline

Call `setText(...)` **before** `addInline(...)`. Spring Mail documentation notes this ordering so mail readers can resolve inline elements. Tests should follow the exact construction sequence used in production rather than writing test setup in a different order and mistaking it for a Jakarta Mail bug.

## 14. Test attachments with real bytes, not Base64 Strings

MIME can encode attachments as base64. However, `Part.getInputStream()` typically returns the content after transfer-encoding decoding. Therefore, if the goal is checking attachment bytes, compare:

```java
byte[] original = new byte[] {
        10, 20, 30, 40, (byte) 200
};

helper.addAttachment(
        "data.bin",
        new ByteArrayResource(original),
        "application/octet-stream"
);

message.saveChanges();
Part filePart = MimeTestParts.requireDisposition(
        MimeTestParts.flatten(message),
        Part.ATTACHMENT
);

assertArrayEquals(
        original,
        filePart.getInputStream().readAllBytes()
);
```

Avoid:

```java
// Easily couples to transfer encoding, line wrapping, and boundaries.
assertTrue(rawMimeString.contains(
        Base64.getEncoder().encodeToString(original)));
```

Raw MIME may wrap base64 lines, choose another encoding, or change serialization details. Byte-level decoded comparison is far less brittle.

### MIME type does not prove valid file format

`Content-Type: application/pdf` is only a type declaration. If the input bytes are not a valid PDF, `MimeMessageHelper` does not turn them into one. MIME tests should verify bytes and type declarations; PDF-generation tests should verify PDF content in a separate test layer.

## 15. Verify Content-Disposition

Common dispositions:

- `Part.ATTACHMENT`: attached file.
- `Part.INLINE`: part intended for inline display with the body.
- `null` or another value: not necessarily an error, depending on part type.

Example:

```java
Part attachment = MimeTestParts.requireDisposition(
        parts, Part.ATTACHMENT);
assertTrue(attachment.isMimeType("application/octet-stream"));

Part inline = MimeTestParts.require(parts, "image/png");
assertTrue(Part.INLINE.equalsIgnoreCase(
        inline.getDisposition()));
```

Do not require all `text/plain` and `text/html` parts to carry a `Content-Disposition`. Many valid body parts have no explicit disposition.

## 16. Count attachments in a multi-part message

A message may contain an inline logo, multiple PDFs, and text content. Counting every `BodyPart` does not tell you the attachment count:

```text
multipart/mixed
  +-- multipart/related
  |     +-- text/plain
  |     +-- text/html
  |     +-- image/png (inline)
  +-- application/pdf (attachment)
  +-- text/csv (attachment)
```

Count by disposition instead:

```java
int attachmentCount = 0;
for (Part part : MimeTestParts.flatten(message)) {
    if (Part.ATTACHMENT.equalsIgnoreCase(
            part.getDisposition())) {
        attachmentCount++;
    }
}

assertEquals(2, attachmentCount);
```

Note that this test relies on a composer policy that always marks attached files with disposition attachment. An inbound email from an external source may carry a filename without setting a disposition, so a general-purpose parser needs broader logic.

## 17. MIME round-trip test: serialize then re-parse

Inspecting `MimeMessage` directly checks the object model. However, if the goal is ensuring the message survives serialization, write the bytes to a buffer **only in tests with dummy data**, then construct a new message from those bytes.

```java
import jakarta.mail.Session;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.List;
import java.util.Properties;
import static org.junit.jupiter.api.Assertions.*;

void assertMimeRoundTrip(MimeMessage original)
        throws Exception {

    original.saveChanges();

    ByteArrayOutputStream buffer = new ByteArrayOutputStream();
    original.writeTo(buffer);

    Session session = Session.getInstance(new Properties());
    MimeMessage parsed = new MimeMessage(
            session,
            new ByteArrayInputStream(buffer.toByteArray())
    );

    List<Part> parsedParts = MimeTestParts.flatten(parsed);
    assertTrue(MimeTestParts.contains(
            parsedParts, "multipart/alternative"));
    assertTrue(MimeTestParts.contains(
            parsedParts, "text/plain"));
    assertTrue(MimeTestParts.contains(
            parsedParts, "text/html"));
}
```

This is still a **unit test** because there is no SMTP connection. It verifies Jakarta Mail can serialize/re-parse the message and all parts remain intact.

Never call `writeTo(System.out)` or dump real emails to logs. For production messages, raw MIME may contain Bcc, reset tokens, attachments, and PII; tests should use only dummy fixtures.

## 18. Why not compare raw MIME as a single string?

A brittle assertion:

```java
assertEquals(expectedFullMimeText, actualFullMimeText);
```

It can fail because:

- MIME boundaries are generated dynamically.
- `Date` changes with time.
- `Message-ID` can vary.
- Header line folding varies.
- MIME parameter ordering or casing changes.
- Text may be encoded as base64 or quoted-printable.
- RFC message line endings differ from string fixtures.

If the goal is business-meaningful results, assert:

```java
assertTrue(MimeTestParts.contains(parts, "text/html"));
assertEquals(expectedHtml,
        MimeTestParts.require(parts, "text/html").getContent());
assertArrayEquals(expectedBytes,
        MimeTestParts.requireDisposition(
                parts, Part.ATTACHMENT)
                .getInputStream().readAllBytes());
```

Use golden-file raw MIME comparisons only when intentionally testing **byte-level serialization formatting**. Even then, control timestamps, Message-IDs, boundaries, and library versions.

## 19. Test sender, recipient, and Subject headers

`MimeMessageHelper` does not only handle the body. Before traversing multiparts, check important headers:

```java
helper.setFrom("no-reply@example.org");
helper.setTo("customer@example.net");
helper.setCc("support@example.org");
helper.setSubject("Result notification");

message.saveChanges();

assertEquals("Result notification", message.getSubject());

InternetAddress[] from =
        (InternetAddress[]) message.getFrom();
assertEquals("no-reply@example.org", from[0].getAddress());

Address[] to = message.getRecipients(
        Message.RecipientType.TO);
assertEquals(1, to.length);
assertEquals("customer@example.net",
        ((InternetAddress) to[0]).getAddress());

Address[] cc = message.getRecipients(
        Message.RecipientType.CC);
assertEquals("support@example.org",
        ((InternetAddress) cc[0]).getAddress());
```

`InternetAddress.getAddress()` verifies the address separately from the display name. For Unicode subjects, `message.getSubject()` returns decoded text, so assert the semantic string instead of raw encoded-words.

Note that `Bcc` may be handled differently when the transport sends the message; never use an in-memory dump to infer whether final recipients see or do not see this header.

## 20. Test text/html containing dynamic data

Suppose a composer renders a confirmation email:

```html
<p>Hello <span th:text="${customerName}">Guest</span></p>
```

After rendering and calling `helper.setText(plain, html)`, unit tests can verify:

1. The plain-text version contains the customer name.
2. The HTML version contains the properly escaped customer name.
3. No template placeholders remain.
4. Backend-generated links are not lost.
5. Content uses UTF-8 charset.

With test input `Nguyễn <Admin>`, an assertion can check that HTML contains `&lt;Admin&gt;` rather than injecting `<Admin>` as an actual tag. However, **HTML escaping belongs to the template engine**, not `MimeMessageHelper` automatically. If unescaped HTML is passed to `setText(..., true)`, the helper does not fix XSS or HTML injection on its own.

Separate template rendering tests from MIME structure tests; an integration-style composer test can combine both to confirm template output was placed into the HTML part properly.

## 21. Separate MailComposer from actual sending

A testable design separates responsibilities:

- **MailComposer:** builds a `MimeMessage` from business data.
- **MailSubmissionService:** receives the message and calls `JavaMailSender.send(...)`.

Example:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class WelcomeMailComposer {

    private final JavaMailSender sender;

    public WelcomeMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public MimeMessage create(
            String recipient,
            String displayName
    ) throws MessagingException {

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, "UTF-8");

        helper.setFrom("welcome@example.org");
        helper.setTo(recipient);
        helper.setSubject("Welcome");
        helper.setText(
                "Hello " + displayName,
                "<p>Hello <strong>" + displayName
                        + "</strong></p>"
        );
        return message;
    }
}
```

This example illustrates separating the composer; in a real application, **escape or render through a template engine** for user data before concatenating into HTML. MIME tests do not replace output-escaping tests.

With this design, unit tests can inspect the `MimeMessage` before sending. It needs no SMTP connection and no mocking of every `MimeMessageHelper` method.

## 22. Test the composer with Mockito

In tests, mock only `JavaMailSender.createMimeMessage()`; the MIME object remains a real Jakarta Mail instance:

```java
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

import java.util.List;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class WelcomeMailComposerTest {

    @Test
    void createsAlternativeContentWithoutSending()
            throws Exception {

        JavaMailSender sender = mock(JavaMailSender.class);
        when(sender.createMimeMessage()).thenAnswer(
                ignored -> new MimeMessage(
                        Session.getInstance(new Properties()))
        );

        WelcomeMailComposer composer =
                new WelcomeMailComposer(sender);

        MimeMessage message = composer.create(
                "recipient@example.net", "Nguyễn An");
        message.saveChanges();

        List<Part> parts = MimeTestParts.flatten(message);

        assertEquals("Welcome", message.getSubject());
        assertTrue(MimeTestParts.contains(
                parts, "multipart/alternative"));
        assertEquals(
                "Hello Nguyễn An",
                MimeTestParts.require(
                        parts, "text/plain").getContent()
        );

        verify(sender, times(1)).createMimeMessage();
        verify(sender, never()).send(any(MimeMessage.class));
    }
}
```

Significance:

- Mockito verifies the composer requests message creation properly.
- `MimeMessage` is a real object, so assertions inspect the actual MIME structure.
- `send(...)` is not called in composer tests.
- No Spring application context is needed when constructor injection suffices.

### Why not mock MimeMessage?

If you mock both `MimeMessage` and `MimeMessageHelper`, you only test the mocked method calls without knowing what parts are actually produced. For multipart testing, **using real in-memory Jakarta Mail objects** is usually far more valuable than low-level mock objects.

## 23. Test the mail-sending service in a separate layer

Once the composer is tested, another unit test can verify the submission service invokes the sender:

```java
public final class MailSubmissionService {

    private final JavaMailSender sender;

    public MailSubmissionService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void submit(MimeMessage message) {
        sender.send(message);
    }
}
```

Test:

```java
@Test
void delegatesMimeMessageToSender() {
    JavaMailSender sender = mock(JavaMailSender.class);
    MimeMessage message = new MimeMessage(
            Session.getInstance(new Properties()));

    MailSubmissionService service =
            new MailSubmissionService(sender);

    service.submit(message);

    verify(sender).send(same(message));
}
```

This test checks **the invocation**, not whether the SMTP server accepted the message. It should accompany composer unit tests and at least one integration test sending to an SMTP test server when end-to-end verification is required.

## 24. Test re-readable resources

`addInline(...)` and `addAttachment(...)` accept resource/`InputStreamSource` types. During sending or serialization, the data source may need to be opened multiple times. Therefore, prefer re-readable resources.

### ByteArrayResource

```java
byte[] content = new byte[] {10, 20, 30, 40};

helper.addAttachment(
        "data.bin",
        new ByteArrayResource(content),
        "application/octet-stream"
);
```

`ByteArrayResource` creates a fresh `ByteArrayInputStream` every time it is requested; well suited for small in-memory content.

### Be careful with InputStreamResource

`InputStreamResource` typically wraps an already-open stream, which is **single-use** in many situations. If Jakarta Mail needs to read it again, it may fail or receive an exhausted stream.

Do not rely on a test that serializes only once to conclude that a resource will work reliably during actual sending.

### A test checking double serialization

```java
byte[] bytes = new byte[] {1, 2, 3, 4, 5};
MimeMessage message = newMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
helper.setText("Attached file");
helper.addAttachment(
        "sample.bin",
        new ByteArrayResource(bytes),
        "application/octet-stream"
);
message.saveChanges();

for (int attempt = 0; attempt < 2; attempt++) {
    ByteArrayOutputStream output = new ByteArrayOutputStream();
    message.writeTo(output);

    MimeMessage parsed = new MimeMessage(
            Session.getInstance(new Properties()),
            new ByteArrayInputStream(output.toByteArray())
    );

    Part attachment = MimeTestParts.requireDisposition(
            MimeTestParts.flatten(parsed),
            Part.ATTACHMENT
    );

    assertArrayEquals(
            bytes,
            attachment.getInputStream().readAllBytes()
    );
}
```

This test is useful for in-memory byte sources. It does not prove every real-world resource is re-readable; if the application attaches files from object storage, database, or filesystem, test with the actual resource type used in production.

## 25. Test multiple attachments

With two files:

```java
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(pdfFixture),
        "application/pdf"
);

helper.addAttachment(
        "items.csv",
        new ByteArrayResource(csvFixture),
        "text/csv"
);
```

A test should verify:

1. There are exactly two parts with disposition `attachment`.
2. One part has MIME type `application/pdf` and filename `invoice.pdf`.
3. The other part is `text/csv` with filename `items.csv`.
4. Bytes read back from each part match the fixtures.
5. HTML/text bodies still exist; adding attachments did not drop alternative parts.

Do not pick "the second attachment" purely by root index if tests do not care about ordering. Match by disposition + filename or fixture identifier to avoid coupling to nesting position.

### Duplicate filenames can be valid business cases

Two attachments can share the same filename while carrying different data. If the application requires unique filenames, that is **business validation** and should have its own test. Jakarta Mail does not enforce that business rule automatically.

## 26. Test multipart modes with a case matrix table

You can build a matrix:

| Content | Mode | What to assert |
| --- | --- | --- |
| Plain text only | NO | Content is text; multipart not required |
| Text + HTML | Multipart | Has `multipart/alternative`, both bodies correct |
| HTML + inline image | RELATED or MIXED_RELATED | Has image part and matching CID |
| Text + attachment | MIXED or MIXED_RELATED | Has attachment disposition and bytes |
| HTML + inline + attachment | MIXED_RELATED | Has matching mixed/related/alternative branches |
| Multiple attachments | MIXED_RELATED | Count, filenames, types, bytes correct |

There is no need to write one giant test with dozens of unrelated assertions. Splitting tests by behavior makes it obvious whether a bug lies in multipart mode, body, inline items, or attachments.

Examples of focused test names:

```text
plainTextDoesNotRequireMultipart()
alternativeContainsPlainAndHtml()
htmlUsesUtf8Charset()
mixedRelatedContainsInlineImage()
attachmentRetainsOriginalBytes()
severalAttachmentsKeepTheirMetadata()
serializedMessageCanBeParsedAgain()
```

## 27. Negative tests and MIME preparation errors

Some errors occur **before SMTP runs**:

- Invalid email address per application validation.
- Filename or content ID violating policy.
- Missing or unreadable resource.
- Template missing required data.
- Failure to build a MIME part from the data source.

Do not assume every failure becomes `MailSendException`; building a `MimeMessage` can throw `MessagingException`, or Spring may wrap preparation failures in `MailPreparationException` when using `MimeMessagePreparator`.

### Test application validation

If a service enforces validated recipients and attachments under 10 MB:

```java
@Test
void rejectsOversizedAttachmentBeforeBuildingMail() {
    byte[] oversized = new byte[10 * 1024 * 1024 + 1];

    assertThrows(
            AttachmentTooLargeException.class,
            () -> mailPolicy.validateSize(oversized.length)
    );
}
```

`AttachmentTooLargeException` and `mailPolicy` here are application-defined components. The test verifies **the validation layer** blocks invalid content, not a mandatory exception provided by `MimeMessageHelper`.

### Test resource failures

For resources backed by filesystem or object storage, define what the system must do:

- Report a clear error when unreadable.
- Avoid creating an empty email or silently sending without the file.
- Record error state on the notification.
- Retry or fail depending on error type and business policy.

Unit tests can use a fake `InputStreamSource` that throws `IOException` when opening the stream; remember that reading the resource may happen only during serialization or send, not necessarily during `addAttachment(...)`.

## 28. What unit tests cannot prove

A test can pass all `MimeMessage` assertions while the system still has issues:

| Issue | Why unit tests are insufficient | Additional test |
| --- | --- | --- |
| Wrong SMTP host/port | No real connection opened | Staging environment integration test |
| TLS/STARTTLS failure | No handshake performed | SMTP test with TLS |
| Provider size limits | Server quotas not checked | Integration/configuration test |
| Server rejects recipient | No SMTP RCPT response | SMTP test with rejection rules |
| Gmail/Outlook render differently | No mail client executed | Visual/client compatibility test |
| Email lands in spam | Depends on deliverability and policy | Provider diagnostics |
| DKIM/SPF/DMARC | Depends on domain and relay config | Provider/domain tests |
| Email reaches Inbox | SMTP acceptance differs from delivery | Provider event/mailbox test |
| Duplicate sends after timeout | Depends on retry and system state | Workflow/idempotency test |

Do not name a test `emailIsDeliveredSuccessfully()` when it only verifies that `MimeMessageHelper` created an HTML part.

## 29. Short integration test with a simulated SMTP server

After unit tests, an integration test can:

1. Start a test SMTP server such as GreenMail or Mailpit.
2. Configure `JavaMailSender` to send to the test server's host/port.
3. Build the email with the real composer.
4. Call `mailSender.send(message)`.
5. Read the message received by the test SMTP server.
6. Parse MIME and verify subject, recipients, HTML/text, and attachments.

```text
Spring Mail Composer
       |
       v
JavaMailSender.send(...)
       |
       v
SMTP test server
       |
       v
Received MimeMessage
       |
       v
Assert MIME parts + bytes
```

This test additionally checks serialization/SMTP submission in a test environment. It still does not prove the email was sent through a production provider or renders properly on every mail client.

Never use real customer addresses or production SMTP for this test. For attachments, use only fixtures containing no sensitive data.

## 30. Assertions prone to flakiness

| Assertion to avoid | Why it breaks easily | Better alternative |
| --- | --- | --- |
| Comparing full raw MIME | Boundary, date, Message-ID vary | Parse MIME then assert content |
| Comparing raw `Content-Type` strings | Casing, quotes, parameter order | `isMimeType` / `ContentType` |
| Assuming HTML is at `root.getBodyPart(0)` | Tree can have multiple nested levels | Traverse recursively |
| Comparing raw base64 strings | Line wrapping may differ | Read decoded `InputStream` |
| Asserting specific boundary names | Boundaries are auto-generated | Assert the right `multipart/*` type |
| Counting all body parts as attachments | Includes HTML, text, inline parts | Count by disposition |
| Asserting fixed `Message-ID` values | Header may be auto-generated | Assert presence if required |
| `Thread.sleep` waiting for mail send | Timing-dependent | Future, latch, or test server wait |
| Only verifying `send` was called | Does not inspect message contents | Capture/inspect `MimeMessage` |

When a new Jakarta Mail version changes encoding details while decoded content and MIME semantics stay intact, a well-written unit test should still pass.

## 31. Checklist for a multipart test

**Setup**

- [ ] Create `Session` and `MimeMessage` in memory.
- [ ] Choose multipart mode intentionally.
- [ ] Use dummy recipients, names, and attachment fixtures.
- [ ] Never call production SMTP.

**Text/HTML**

- [ ] `multipart/alternative` exists when using plain + HTML.
- [ ] Text and HTML parts have the right MIME types.
- [ ] Decoded content matches.
- [ ] Charset/Unicode are appropriate.
- [ ] Template escaping is tested separately.

**Inline**

- [ ] HTML contains the expected `cid:...` URI.
- [ ] Inline part exists with the matching `Content-ID`.
- [ ] Image MIME type and bytes are correct.
- [ ] `multipart/related` structure is appropriate.

**Attachments**

- [ ] Attachment has the appropriate disposition.
- [ ] Filename and Content-Type follow policy.
- [ ] Attachment count is exact.
- [ ] Decoded bytes match the fixture.
- [ ] Resource is re-readable when needed.

**Stability**

- [ ] Do not compare fixed boundaries/Message-IDs.
- [ ] Do not rely on root index unnecessarily.
- [ ] Include a round-trip test when serialization must be verified.
- [ ] Keep unit tests distinct from SMTP integration tests.

## 32. Common testing mistakes

### Mistake 1 — Blindly casting root content to Multipart

```java
Multipart multipart = (Multipart) message.getContent();
```

This fails on single-part messages. Verify `message.isMimeType("multipart/*")` first, or use a conditional tree-traversal helper.

### Mistake 2 — Always assuming part 0 is HTML

In `multipart/alternative`, plain text usually precedes HTML. In `mixed/related`, part 0 may be another `Multipart`. Search by MIME type inside the right container.

### Mistake 3 — Using InputStreamResource from an already-consumed stream

A single-read stream can cause attachments to fail on re-serialization. Prefer `ByteArrayResource` or a source that opens fresh streams; test with multiple serialize/read cycles where appropriate.

### Mistake 4 — Comparing raw boundaries

Boundaries usually change between runs. Tests should assert the presence of `multipart/alternative`, `multipart/related`, or `multipart/mixed`, never `boundary="abc123"`.

### Mistake 5 — Testing HTML with plain-text assertions

`helper.setText(html, true)` creates an HTML-only body, whereas `helper.setText(plain, html)` creates both representations. If a text fallback is wanted, use the right overload; tests should require both parts.

### Mistake 6 — Testing mail templates with real data

Never use real customer bodies, Bcc addresses, or real tokens in tests or logs. Dummy fixtures are sufficient for verifying charsets, structure, encoded headers, and attachments.

### Mistake 7 — Assuming passing tests mean delivered email

Unit tests only prove the message was built properly. Even a successful `JavaMailSender.send` only reflects observed SMTP submission, not guaranteed Inbox delivery.

## 33. Practice scenarios

### A. Email has HTML but no plain-text version

Code calls `helper.setText("<p>HTML</p>", true)`. A test expecting `multipart/alternative` and `text/plain` fails.

**Explanation:** this overload sets only the HTML body and does not auto-generate a plain-text fallback. Use `setText(plain, html)` on a multipart message when business rules require both.

### B. HTML test passes but inline logo is missing

The test only checks that an `image/png` part exists without checking Content-ID.

**Explanation:** the presence of an image does not mean `cid:logo` resolves to it. Tests must match the HTML value against the `Content-ID` header, and verify nesting and attachment bytes.

### C. Attachment test fails on the second serialization

Code uses a single-read stream source.

**Explanation:** serialization may require re-reading the resource. Switch to `ByteArrayResource` or a resource opening fresh streams, then test repeated reads with a fixture.

### D. Test fails after upgrading Jakarta Mail

Content-Type changed from `text/html; charset=UTF-8` to `text/html; charset="UTF-8"`, even though the email still displays properly.

**Explanation:** raw string assertion was too brittle. Use `ContentType.getBaseType()` and `getParameter("charset")`.

### E. Test counts three body parts and concludes there are three attachments

The message contains text, HTML, and one PDF.

**Explanation:** body part does not mean attachment. Count by disposition and type, while text/HTML are content parts.

### F. Test verifies `sender.send(message)` yet production loses HTML

The Mockito test only checks that the sender was called.

**Explanation:** that test did not verify the composer. Use a real `MimeMessage` in unit tests, parse `multipart/alternative`, and verify HTML content.

### G. MIME round-trip passes yet Outlook still breaks

The message serializes and re-parses via Jakarta Mail, yet Outlook renders differently.

**Explanation:** parser round-trips do not replace mail-client compatibility tests. Send a fixture to a test Outlook client and inspect nesting, CID, disposition, and HTML rendering.

## 34. Conclusion

Testing `MimeMessageHelper` with multipart should focus on **meaningful MIME behavior**: having the right `multipart/alternative` for plain text and HTML, the right `mixed/related` structure for inline images and attachments, accurate Content-ID, charset, filename/disposition, and decoded bytes. Creating a `MimeMessage` via in-memory Jakarta Mail keeps unit tests fast, SMTP-free, and avoids mocking `Multipart` or `BodyPart`.

To keep tests maintainable, use a MIME-tree traversal utility, parse `Content-Type` instead of comparing raw strings, avoid relying on auto-generated boundaries/Message-IDs, and verify attachments via decoded bytes. Separating `MailComposer` from sending lets unit tests verify message construction, while integration tests with a simulated SMTP server test transport send/receive behavior.

A passing multipart unit test proves **the message was built as expected**, not that it was sent or reached the Inbox. Keeping this boundary clear lets tests catch structural bugs before deployment while avoiding false alarms from unimportant encoding or serialization details.
