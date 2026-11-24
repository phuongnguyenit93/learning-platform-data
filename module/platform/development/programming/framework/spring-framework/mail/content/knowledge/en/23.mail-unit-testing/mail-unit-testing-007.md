# Reading MimeMessage in Tests and Verifying Headers

When using **Spring Framework Mail**, a solid unit test does more than check that `JavaMailSender.send(...)` was called. It also verifies that **the email was prepared properly**: sender and recipient addresses, subject, `Reply-To`, application headers, charset, plain-text/HTML content, and MIME structure when attachments are present.

In Java, complex emails are typically represented by `jakarta.mail.internet.MimeMessage`. Spring helps build and populate messages through `JavaMailSender` and `MimeMessageHelper`. Unit tests can use **Mockito** to avoid real SMTP connections while still creating a real `MimeMessage` object and reading back its properties with Jakarta Mail.

Target workflow:

~~~text
OrderReceiptMailer
    |
    +-- JavaMailSender.createMimeMessage()
    |       -> real MimeMessage, in-memory only
    |
    +-- MimeMessageHelper.setFrom/setTo/setSubject/setText
    |       -> headers and MIME parts are set
    |
    +-- JavaMailSender.send(mimeMessage)
            -> Mockito captures it, no SMTP connection is made
            -> Test reads MimeMessage and asserts each property
~~~

The goal of this lesson is to practice reading `MimeMessage` in tests, understand the right APIs for reading headers, verify MIME content, and avoid assertions that break due to how Jakarta Mail encodes or serializes messages.

## 1. Test at the right boundary

Suppose the application sends an order confirmation email:

- `From`: `orders@notify.example.com`;
- `To`: customer address;
- `Cc`: finance department;
- `Bcc`: audit mailbox;
- `Reply-To`: support team;
- `Subject`: Vietnamese subject containing the order number;
- `X-Template-Id`: template identifier for diagnostics;
- body containing both plain text and HTML.

A simple assertion:

~~~java
verify(mailSender).send(any(MimeMessage.class));
~~~

only proves the service called a `send` overload with a matching object type. It **does not prove** the email goes to the right person, has the right subject, or includes all headers.

Conversely, unit tests **cannot** prove the SMTP server accepted the email or that it landed in the Inbox; they use no real SMTP connection.

### 1.1. Related test types

| Test type | What it verifies | Cannot claim |
| --- | --- | --- |
| Unit test with Mockito + real MimeMessage | Mail service API builds From/To/Subject/headers/MIME properly | SMTP credentials, network, delivery |
| Renderer unit test | Template turns data into proper plain text/HTML | Successful SMTP send |
| Integration test with SMTP test server | SMTP protocol, message submitted to simulated server | Inbox delivery at real providers |
| Provider sandbox/integration test | SMTP/API behavior, authentication, quotas in test env | All mailbox providers always accept mail |
| Provider event/delivery monitoring | Delivery/bounce per provider telemetry | Recipient actually read the message |

For **unit testing**, the lightest approach is mocking transport and inspecting the MIME object built by the service.

## 2. Distinguish MimeMessage, MimeMessageHelper, and JavaMailSender

| Component | Role |
| --- | --- |
| `JavaMailSender` | Spring interface to create and send `MimeMessage` |
| `MimeMessage` | Jakarta Mail object holding MIME headers and content |
| `MimeMessageHelper` | Utility API for setting From, To, Cc, Bcc, Reply-To, Subject, text, attachments |
| Jakarta Mail `Session` | Configuration/context used when creating MimeMessage |
| `Transport` | Component actually speaking SMTP during real sending |
| `ArgumentCaptor<MimeMessage>` | Mockito tool capturing the message passed to the mock |

### 2.1. Mock only the sender, not MimeMessage

A common mistake:

~~~java
@Mock MimeMessage mimeMessage;
@Mock JavaMailSender mailSender;
~~~

If you mock `MimeMessage` as well, calls like `setHeader`, `setRecipients`, and `setContent` on the mock do not store data automatically. Tests calling `getSubject()` or `getRecipients()` afterward receive `null`, unless you write extensive unnecessary stubbing.

Create a **real in-memory MimeMessage** instead:

~~~java
Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
~~~

When the service calls `MimeMessageHelper`, Jakarta Mail stores real data on the object. Mocking `JavaMailSender` only prevents SMTP connections while letting message construction run for real.

### 2.2. No SMTP host needed to create MimeMessage

~~~java
Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
~~~

This opens no socket and needs no username/password. `Session` simply constructs the message object. In unit tests, there is no need to configure `mail.smtp.host` just to inspect headers.

## 3. Dependencies for unit tests

A typical Spring Boot project has:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Or Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The Spring Boot test starter typically provides JUnit Jupiter, Mockito, and AssertJ through appropriate dependency management. Without Spring Boot, declare matching dependencies for your project's Spring/Jakarta Mail/JUnit/Mockito versions.

**Package note:** Spring Framework 6 / Spring Boot 3 and above use Jakarta Mail with `jakarta.mail.*` imports. Spring 5 or older JavaMail projects may use `javax.mail.*`. Never mix both namespaces in the same example/codebase if runtime dependencies are incompatible.

## 4. Illustrative service under test

Consider an order-receipt mail service. To focus on MIME/headers, the service accepts pre-rendered valid plain text and HTML from a renderer; it performs no database queries or template rendering.

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderReceiptMailer {
    private final JavaMailSender mailSender;

    public OrderReceiptMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReceipt(
            String recipient,
            String orderNumber,
            String plainText,
            String htmlText) {

        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message,
                    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                    StandardCharsets.UTF_8.name()
            );

            helper.setFrom("orders@notify.example.com");
            helper.setTo(recipient);
            helper.setCc("finance@example.com");
            helper.setBcc("audit@example.com");
            helper.setReplyTo("support@example.com");

            helper.setSubject(
                    "Xác nhận đơn hàng " + orderNumber);
            helper.setText(plainText, htmlText);

            message.setHeader("X-Template-Id", "order-receipt");
            message.setHeader("X-Notification-Type", "ORDER_RECEIPT");
        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Cannot prepare order receipt email", ex);
        }

        mailSender.send(message);
    }
}
~~~

Assumptions:

- To/From/Cc/Bcc emails are addresses already resolved and validated at the application boundary.
- `orderNumber` is already validated by domain rules.
- `plainText` and `htmlText` are produced by a safe renderer with proper escaping; never insert unescaped user-supplied HTML.
- `orders@notify.example.com`, `finance@example.com`, and `audit@example.com` are illustrative addresses only.

In production designs, sender identity, audit addresses, Reply-To, and template IDs may come from per-tenant, business-domain, or sending-profile configuration. Hardcoding them in the example simply clarifies which headers to test.

## 5. Write unit tests with Mockito and JUnit 5

Tests can use `@ExtendWith(MockitoExtension.class)` and mock `JavaMailSender`.

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class OrderReceiptMailerTest {

    @Mock
    JavaMailSender mailSender;

    OrderReceiptMailer mailer;

    @BeforeEach
    void setUp() {
        when(mailSender.createMimeMessage())
                .thenAnswer(invocation -> new MimeMessage(
                        Session.getInstance(new Properties())
                ));

        mailer = new OrderReceiptMailer(mailSender);
    }

    @Test
    void sendsOneMimeMessage() {
        mailer.sendReceipt(
                "alice@example.net",
                "A123",
                "Đơn hàng A123 đã xác nhận.",
                "<p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>"
        );

        verify(mailSender, times(1))
                .send(any(MimeMessage.class));
    }
}
~~~

Key points to understand:

- `mailSender` is a mock, so calling `send(...)` makes no SMTP connection.
- `createMimeMessage()` is stubbed to return a **real MimeMessage**.
- Each creation call yields a new object, reducing the risk of tests interfering with each other.
- There is no need for `@SpringBootTest` or starting the entire application context just to test a constructor-injected service.
- Mockito's default mock for `void send(...)` does nothing unless stubbed otherwise.

The test above only checks invocation count. The next step is **capturing** the outbound object.

## 6. Capture MimeMessage with ArgumentCaptor

~~~java
import jakarta.mail.internet.MimeMessage;
import org.mockito.ArgumentCaptor;

@Test
void capturesPreparedMessage() throws Exception {
    mailer.sendReceipt(
            "alice@example.net",
            "A123",
            "Đơn hàng A123 đã xác nhận.",
            "<p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>"
    );

    ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);

    verify(mailSender).send(captor.capture());

    MimeMessage actual = captor.getValue();
    assertNotNull(actual);
    assertEquals(
            "Xác nhận đơn hàng A123",
            actual.getSubject()
    );
}
~~~

`ArgumentCaptor` retrieves **the exact object** passed to `send(...)`. We then use the Jakarta Mail API to inspect the actual data.

### 6.1. Why is getSubject() better than reading the raw Subject header?

A Vietnamese subject may be encoded in MIME syntax:

~~~text
Subject: =?UTF-8?B?...?=
~~~

This is an illustrative encoded-word format, not a specific subject string.

`MimeMessage.getSubject()` returns the subject already decoded for Java code. Therefore:

~~~java
assertEquals("Xác nhận đơn hàng A123", actual.getSubject());
~~~

is far more stable than comparing `actual.getHeader("Subject", null)` against raw Vietnamese text. Tests should assert **display semantics**, without depending on whether the library picks Base64 or Quoted-Printable for headers.

## 7. Read From, To, Cc, Bcc, and Reply-To

Jakarta Mail provides:

~~~java
Address[] getFrom();
Address[] getRecipients(Message.RecipientType type);
Address[] getReplyTo();
~~~

### 7.1. From

~~~java
import jakarta.mail.Address;
import jakarta.mail.internet.InternetAddress;

Address[] from = actual.getFrom();
assertNotNull(from);
assertEquals(1, from.length);

InternetAddress sender = (InternetAddress) from[0];
assertEquals(
        "orders@notify.example.com",
        sender.getAddress()
);
~~~

Avoid `from[0].toString()` when the address has a display name, for example:

~~~text
"Cửa hàng" <orders@notify.example.com>
~~~

`toString()` can include both name and encoding, so if you only want to verify the mailbox, use `InternetAddress.getAddress()`.

### 7.2. To, Cc, and Bcc

~~~java
import jakarta.mail.Message;

Address[] to = actual.getRecipients(Message.RecipientType.TO);
Address[] cc = actual.getRecipients(Message.RecipientType.CC);
Address[] bcc = actual.getRecipients(Message.RecipientType.BCC);

assertEquals(
        "alice@example.net",
        ((InternetAddress) to[0]).getAddress()
);
assertEquals(
        "finance@example.com",
        ((InternetAddress) cc[0]).getAddress()
);
assertEquals(
        "audit@example.com",
        ((InternetAddress) bcc[0]).getAddress()
);
~~~

If the message has no recipients in a given group, the method can return `null`. Never access `.length` without checking first.

Example checking there is no Cc:

~~~java
Address[] cc = actual.getRecipients(Message.RecipientType.CC);
assertTrue(cc == null || cc.length == 0);
~~~

### 7.3. Reply-To

~~~java
Address[] replyTo = actual.getReplyTo();
assertNotNull(replyTo);
assertEquals(
        "support@example.com",
        ((InternetAddress) replyTo[0]).getAddress()
);
~~~

Note: `MimeMessage.getReplyTo()` can fall back to the From address when **no Reply-To header exists**. If the test needs to verify the service **explicitly set a Reply-To header**, also check:

~~~java
assertNotNull(actual.getHeader("Reply-To"));
~~~

Seeing `getReplyTo()` return an address matching From is not enough on its own to prove the header was set.

### 7.4. Multiple recipients: compare as a set when order is not in the contract

For a To list, do not force ordering when the business contract specifies only the recipient set. Helper:

~~~java
import jakarta.mail.Address;
import jakarta.mail.internet.InternetAddress;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

static Set<String> mailboxes(Address[] addresses) {
    if (addresses == null) {
        return Set.of();
    }

    return Arrays.stream(addresses)
            .map(address -> ((InternetAddress) address).getAddress())
            .collect(Collectors.toSet());
}
~~~

Assert:

~~~java
assertEquals(
        Set.of("alice@example.net", "bob@example.net"),
        mailboxes(actual.getRecipients(Message.RecipientType.TO))
);
~~~

When detecting duplicate addresses matters, using only a `Set` hides duplicates. Compare list size or element counts before converting to a set.

### 7.5. Do not misunderstand Bcc

In a **pre-send MimeMessage**, `getRecipients(BCC)` can return Bcc addresses because the message object still needs to know the envelope recipients. When an email is transmitted, the Bcc header is typically stripped from the copy shown to recipients by transport/provider handling.

Therefore:

- Pre-send unit tests can assert `getRecipients(BCC)` to verify the service prepared the right blind recipients.
- **Do not** assert that the pre-send `MimeMessage` lacks a Bcc header when the service intentionally sets Bcc.
- This unit test **does not prove** the final recipient copy hides Bcc; verifying transmission/delivery behavior requires an appropriate SMTP/provider test.
- Never copy the Bcc list into To/Cc or public custom headers.

## 8. Read custom headers

An application may set custom headers for routing or diagnostics:

~~~java
message.setHeader("X-Template-Id", "order-receipt");
message.setHeader("X-Notification-Type", "ORDER_RECEIPT");
~~~

Read back:

~~~java
String[] templateHeaders =
        actual.getHeader("X-Template-Id");

assertNotNull(templateHeaders);
assertEquals(1, templateHeaders.length);
assertEquals("order-receipt", templateHeaders[0]);
~~~

Or retrieve as a single string:

~~~java
assertEquals(
        "ORDER_RECEIPT",
        actual.getHeader("X-Notification-Type", null)
);
~~~

### 8.1. getHeader(name) and getHeader(name, delimiter)

| Method | Result |
| --- | --- |
| `getHeader("X-Template-Id")` | `String[]` array of header values, possibly `null` |
| `getHeader("X-Template-Id", null)` | A joined string per API semantics, possibly `null` |
| `getAllHeaders()` | Enumeration of existing headers |
| `getMatchingHeaders(names)` | Enumeration of headers matching the given names |
| `getNonMatchingHeaders(names)` | Enumeration of remaining headers |

Header names are **case-insensitive** by protocol. Query by header name instead of parsing the entire raw message and expecting specific casing.

### 8.2. Headers can appear multiple times

Some headers can carry multiple values. If the service uses `addHeader(...)` instead of `setHeader(...)`, new values are appended rather than overwriting existing ones.

~~~java
message.addHeader("X-Tag", "order");
message.addHeader("X-Tag", "important");
~~~

When asserting:

~~~java
assertArrayEquals(
        new String[] { "order", "important" },
        message.getHeader("X-Tag")
);
~~~

If the contract does not mandate order, assert the value set instead of hardcoding order. Avoid joining multiple values into one string for comparison when delimiters could introduce ambiguity.

### 8.3. Headers can be folded across multiple lines

Long headers may be **folded** per MIME/RFC rules, for example:

~~~text
X-Long-Info: first part
 second part
~~~

Do not compare the entire message verbatim as one string when you only want to verify a meaningful header. Use the `getHeader` API, or re-parse a serialized MimeMessage in a dedicated serialization test.

## 9. Test Vietnamese subjects and charsets

Emails can contain Unicode in:

- Subject;
- From/To display names;
- plain-text body;
- HTML body;
- attachment filenames.

With `MimeMessageHelper(..., "UTF-8")`, for example:

~~~java
helper.setSubject("Xác nhận đơn hàng A123");
~~~

Assert directly:

~~~java
assertEquals(
        "Xác nhận đơn hàng A123",
        actual.getSubject()
);
~~~

If you inspect the raw header, you may see an encoded-word. Do not force the raw header to contain literal `"Xác nhận"` UTF-8 bytes as written in source code.

### 9.1. Content-Type and charset

A content part may have:

~~~text
Content-Type: text/plain; charset=UTF-8
~~~

or:

~~~text
Content-Type: text/html; charset=UTF-8
~~~

In a multipart message, the **root Content-Type** is usually `multipart/*`, not `text/plain` or `text/html`. Therefore, checking:

~~~java
assertTrue(actual.isMimeType("multipart/*"));
~~~

is better than demanding:

~~~java
assertTrue(actual.isMimeType("text/html")); // Wrong for multipart root.
~~~

To verify charset, inspect the text-containing body part:

~~~java
import jakarta.mail.internet.ContentType;

ContentType type = new ContentType(bodyPart.getContentType());
assertTrue(
        "UTF-8".equalsIgnoreCase(type.getParameter("charset"))
);
~~~

This snippet illustrates checking a `bodyPart` containing text. In real tests, the charset parameter casing may be normalized by the library; what matters is that the charset decodes properly, not character-for-character equality of the raw Content-Type string.

### 9.2. Avoid brittle Content-Transfer-Encoding assertions

For Unicode, the library may pick `quoted-printable` or `base64` depending on content, version, and serialization steps.

Typically assert:

- decoded Subject via `getSubject()`;
- decoded body string via `getContent()`;
- charset is UTF-8 or the expected encoding.

Only assert an exact `Content-Transfer-Encoding` when it is genuinely part of the application contract and the test focuses on MIME serialization.

## 10. Read text/plain and text/html content in multipart

With:

~~~java
helper.setText(
        "Đơn hàng A123 đã xác nhận.",
        "<p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>"
);
~~~

`MimeMessageHelper` may produce nested MIME structures.

Example diagram:

~~~text
MimeMessage
└── multipart/mixed
    └── multipart/related
        └── multipart/alternative
            ├── text/plain; charset=UTF-8
            └── text/html; charset=UTF-8
~~~

This illustrative structure depends on the `MimeMessageHelper` mode, library version, and presence of inline resources/attachments. **Do not write tests that rigidly navigate `getBodyPart(0).getBodyPart(1)`** when the goal is simply verifying plain text and HTML exist.

### 10.1. Traverse the MIME tree instead of guessing positions

Test utility method:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

static boolean hasTextPart(
        Part part,
        String mimeType,
        String expectedSubstring) throws Exception {

    if (part.isMimeType(mimeType)) {
        Object content = part.getContent();
        return content instanceof String text
                && text.contains(expectedSubstring);
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            if (hasTextPart(
                    multipart.getBodyPart(i),
                    mimeType,
                    expectedSubstring)) {
                return true;
            }
        }
    } else if (content instanceof Part nestedPart) {
        return hasTextPart(
                nestedPart,
                mimeType,
                expectedSubstring);
    }

    return false;
}
~~~

This method:

1. If the current part has the target MIME type, reads the content decoded by Jakarta Mail.
2. If the part contains a `Multipart`, iterates through each body part.
3. If the part contains a nested `Part` (for example a nested message), recurses deeper.
4. Does not depend on absolute positions of plain/HTML parts.

This is a testing utility; in production systems processing untrusted external MIME, add size limits and traversal-depth bounds against malicious or oversized payloads.

### 10.2. Test plain and HTML

~~~java
@Test
void containsBothPlainAndHtmlAlternatives() throws Exception {
    mailer.sendReceipt(
            "alice@example.net",
            "A123",
            "Đơn hàng A123 đã xác nhận.",
            "<p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>"
    );

    ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);
    verify(mailSender).send(captor.capture());

    MimeMessage actual = captor.getValue();

    assertTrue(hasTextPart(
            actual,
            "text/plain",
            "Đơn hàng A123 đã xác nhận."
    ));

    assertTrue(hasTextPart(
            actual,
            "text/html",
            "<strong>A123</strong>"
    ));
}
~~~

This test verifies the prepared content; it does not claim HTML will render identically across Gmail, Outlook, and other email clients.

### 10.3. text/plain differs from text/html

Do not assert only HTML and ignore the plain-text part if the application contract requires emails to be readable by non-HTML clients.

Example:

~~~text
Plain:
  Đơn hàng A123 đã xác nhận.

HTML:
  <p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>
~~~

The two versions can format differently yet must convey the same core facts. You can verify that critical business values (order number, amount, link) appear in both instead of asserting character-for-character equality.

## 11. Headers exist at the root and on body parts

In MIME, headers do not live only at the root `MimeMessage`:

~~~text
MimeMessage headers:
  From
  To
  Subject
  MIME-Version
  Content-Type: multipart/mixed

BodyPart headers:
  Content-Type: text/html; charset=UTF-8
  Content-Transfer-Encoding: quoted-printable
~~~

Calling:

~~~java
actual.getHeader("Content-Type");
~~~

reads the **root** Content-Type, which is usually multipart. To check HTML's charset, read `getContentType()` on the **HTML body part**, rather than relying on the root.

Similarly:

- an attachment's `Content-Disposition` lives on the attachment part;
- an inline image's `Content-ID` lives on the image part;
- `Content-Transfer-Encoding` can differ between parts.

This is why MIME tests usually traverse the `Multipart` tree instead of calling only `MimeMessage.getHeader(...)`.

## 12. Verify attachments via MIME structure

Suppose the service attaches an invoice:

~~~java
import org.springframework.core.io.ByteArrayResource;

helper.addAttachment(
        "invoice-A123.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
~~~

An assertion on the root like:

~~~java
assertTrue(actual.isMimeType("application/pdf")); // Wrong for root
~~~

is incorrect. The PDF is a body part inside `multipart/*`.

### 12.1. Locate the attachment part

Illustrative method:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

static boolean hasAttachmentNamed(
        Part part,
        String expectedName) throws Exception {

    String disposition = part.getDisposition();
    if (Part.ATTACHMENT.equalsIgnoreCase(disposition)
            && expectedName.equals(part.getFileName())) {
        return true;
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            if (hasAttachmentNamed(
                    multipart.getBodyPart(i),
                    expectedName)) {
                return true;
            }
        }
    }
    return false;
}
~~~

In tests:

~~~java
assertTrue(
        hasAttachmentNamed(actual, "invoice-A123.pdf")
);
~~~

Notes:

- Unicode filenames may be MIME-encoded; Jakarta Mail may decode them on `getFileName()` depending on configuration/library.
- Attachments in messages from external providers might not have a simple `Content-Disposition` as expected; tests should match the contract of the service building the message.
- Seeing a filename alone does not prove the bytes are right. If strict accuracy is needed, read `part.getInputStream()` and compare a checksum/byte array on the attachment part.
- Never log an entire PDF or secrets in test output.

### 12.2. Inline images differ from attachments

With:

~~~java
helper.addInline(
        "company-logo",
        new ByteArrayResource(pngBytes),
        "image/png"
);
~~~

the service may create a part with headers:

~~~text
Content-ID: <company-logo>
Content-Disposition: inline
Content-Type: image/png
~~~

In HTML, the reference may be `cid:company-logo`.

To test, locate the part with the matching `Content-ID` and MIME type `image/png`. Do not assume the inline image sits at a fixed body-part index. What matters is that the CID referenced in HTML matches the part's content ID.

## 13. Standard headers vs custom headers

Headers with specific meaning at the Internet Message Format/MIME layer:

| Header | Preferred inspection method |
| --- | --- |
| `From` | `getFrom()` and `InternetAddress.getAddress()` |
| `To`, `Cc`, `Bcc` | `getRecipients(RecipientType)` |
| `Reply-To` | `getReplyTo()` and when needed `getHeader("Reply-To")` |
| `Subject` | `getSubject()` to get the decoded string |
| `Sent-Date` / `Date` | `getSentDate()` after the date is set |
| `Message-ID` | `getMessageID()` after saving/serializing appropriately |
| `Content-Type` | `getContentType()` or `isMimeType()` on the exact Part |
| `Content-Disposition` | `Part.getDisposition()` |
| `Content-ID` | `Part.getHeader("Content-ID")` |
| `X-Template-Id` | `getHeader("X-Template-Id")` |

Prefer typed APIs where available. Regex parsing over the whole raw message breaks easily on header folding, encoding, boundaries, and line endings.

### 13.1. Headers must never carry secret data

Never place:

- SMTP passwords;
- OAuth access/refresh tokens;
- plaintext OTP codes;
- secrets used to sign links;
- sensitive payment data;
- unnecessary personal data

into `X-*` headers just for debugging convenience. Headers can be forwarded and stored by many mail servers. Use non-sensitive local job IDs or correlation IDs when tracing is needed.

### 13.2. Header injection

If a header value is built directly from arbitrary input containing CR/LF, there is a **header injection** risk:

~~~text
User input:
  user-supplied-value\r\nBcc: attacker@example.net
~~~

At the application boundary, validate/sanitize inputs properly; never let users control `From`/`Bcc` or policy headers. Unit tests can verify invalid input is rejected and `mailSender.send` is not called.

Do not rely solely on `InternetAddress.validate()` to ensure an address actually exists or will be accepted by an SMTP server; it primarily checks syntax per API rules.

## 14. When should you call saveChanges() in tests?

`MimeMessage` holds in-memory state. Helper operations populate many headers/parts before sending, yet headers such as `Date`, `Message-ID`, `MIME-Version`, or `Content-Transfer-Encoding` may be generated or updated during **saveChanges** or **serialization**.

Example:

~~~java
MimeMessage message = new MimeMessage(
        Session.getInstance(new Properties())
);
// Set From, To, Subject, content...

message.saveChanges();
String messageId = message.getMessageID();
~~~

When `JavaMailSender` is a mock, `send` does not run real preparation/transport. Therefore, if a test inspects the auto-generated `Message-ID` from Jakarta Mail without calling `saveChanges()`, it may see `null` or unexpected values.

**Do not call `saveChanges()` in every test unnecessarily.** For From/To/Subject/custom headers, you can read them immediately after the helper sets them. For serialization tests, make save/serialize an explicit step.

### 14.1. Do not hard-code random Message-IDs

Avoid:

~~~java
assertEquals(
        "<fixed-message-id@example.com>",
        actual.getMessageID()
);
~~~

if the code does not set a fixed Message-ID. The library may generate values containing timestamps, random/counter components, or hostnames. If the contract only requires a Message-ID to exist after serialization:

~~~java
actual.saveChanges();
assertNotNull(actual.getMessageID());
~~~

Do not treat Message-ID as an idempotency key guaranteeing SMTP deduplicates emails; those are separate concepts.

### 14.2. Date and timezones

If the service uses `helper.setSentDate(...)` or `message.setSentDate(...)` with an injected clock, you can assert an exact match against a `Clock.fixed(...)`.

If Jakarta Mail auto-generates Date on save, do not hard-code timestamps from the test machine's clock. Timezones also affect raw header formatting. It is better to:

- inject `Clock` when time is part of the business contract;
- assert `Date` is set, or compare typed `Instant`/`Date` values;
- avoid comparing literal timezone strings in raw headers.

### 14.3. saveChanges() can mutate the message

`saveChanges()` is not merely a "getter." It can create or update headers and MIME metadata. If a test only checks data set by the service, avoid mutating the message before assertions. If a test specifically verifies serialized MIME, call save/serialize intentionally in a dedicated test.

## 15. Serialize MimeMessage when raw MIME inspection is needed

Sometimes you need to inspect actual MIME output, such as checking header folding, boundaries, or whether a parser can read back the saved message.

You can serialize into memory:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

actual.saveChanges();

ByteArrayOutputStream out = new ByteArrayOutputStream();
actual.writeTo(out);

byte[] rawMime = out.toByteArray();
String preview = new String(
        rawMime,
        StandardCharsets.ISO_8859_1
);
~~~

**Never use `preview` to directly assert Vietnamese Unicode display.** Raw MIME contains encoded-words, quoted-printable, base64, and MIME boundaries. ISO-8859-1 only gives a lossless byte-to-string view for inspection; it does not decode MIME content properly.

To test round-trip parsing, re-parse:

~~~java
import java.io.ByteArrayInputStream;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

MimeMessage reparsed = new MimeMessage(
        Session.getInstance(new Properties()),
        new ByteArrayInputStream(rawMime)
);

assertEquals(
        "Xác nhận đơn hàng A123",
        reparsed.getSubject()
);
~~~

Round-trip tests are valuable when the product stores raw MIME for queues/retries or exchanges messages with an independent mail transport.

### 15.1. Why not snapshot the entire raw MIME?

A test like:

~~~java
assertEquals(expectedRawMessage, preview);
~~~

is typically fragile because:

- MIME boundaries can change;
- Date/Message-ID can be generated dynamically;
- header order or folding varies;
- encoding switches between Base64 and Quoted-Printable;
- CRLF and line wrapping depend on the library;
- Jakarta Mail version upgrades can cause diffs without changing message meaning.

Snapshot raw MIME only when byte-level format itself is the contract, such as signing/canonicalization integrations. For business logic, parsed/semantic API assertions are far more durable.

## 16. Verify marketing email headers

Besides From/Subject/Reply-To, marketing emails may require:

~~~text
List-Unsubscribe: <https://offers.example.com/u/opaque-token>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
~~~

In tests, check:

~~~java
assertEquals(
        "<https://offers.example.com/u/opaque-token>",
        actual.getHeader("List-Unsubscribe", null)
);

assertEquals(
        "List-Unsubscribe=One-Click",
        actual.getHeader("List-Unsubscribe-Post", null)
);
~~~

If the URL contains a dynamically generated token, do not hard-code the entire token. Check host, HTTPS scheme, path, signature/expiry per contract, or use a controlled fake token generator.

**Note:** having an unsubscribe header does not mean the endpoint actually works or that the provider/email client will render an unsubscribe button. Those require separate integration/behavior tests. Moreover, do not add marketing headers to transactional emails unless policy explicitly permits it.

### 16.1. Headers usually added by the provider after submission

Some headers only appear on messages after passing through SMTP/ESP, such as:

- `Received`;
- `Authentication-Results` added by the mail receiver;
- `DKIM-Signature` when the ESP performs signing;
- `Return-Path` handled during delivery;
- provider-specific tracking/delivery headers.

Pre-SMTP service unit tests **should not require** those headers to be present unless the application service itself is responsible for creating them.

You cannot prove SPF/DKIM/DMARC pass simply by reading a pre-send `MimeMessage`. Appropriate DNS/ESP/receiver tests are needed.

## 17. Verify addresses with display names

A From address can be built as:

~~~java
helper.setFrom(
        new InternetAddress(
                "orders@notify.example.com",
                "Cửa hàng Ví dụ",
                "UTF-8"
        )
);
~~~

In tests:

~~~java
InternetAddress from =
        (InternetAddress) actual.getFrom()[0];

assertEquals(
        "orders@notify.example.com",
        from.getAddress()
);
assertEquals("Cửa hàng Ví dụ", from.getPersonal());
~~~

If inspecting the raw `From` header, the display name may be RFC 2047 encoded. `getPersonal()` usually returns the decoded name. Tests should verify mailbox and personal name **separately**, instead of comparing a single `toString()` string.

### 17.1. Multiple From/Sender

In most application emails, `From` is a single authorized sending mailbox. RFCs have specific rules when multiple mailboxes appear in From and `Sender` is used. Avoid constructing that setup unless you understand protocol requirements and provider policies.

If the service sets `Sender`, test that header separately; `getFrom()` and `getSender()` do not serve the same role. With Spring Mail, From/Reply-To are typically the primary values to check first.

## 18. Test not sending when validation fails

Header tests should go hand in hand with tests verifying **no message is built/sent** when a request is invalid.

Example where an application boundary rejects an unauthorized address:

~~~java
@Test
void rejectsUnauthorizedSenderBeforeSending() {
    assertThrows(
            IllegalArgumentException.class,
            () -> applicationService.submitMail(
                    "attacker@example.net",
                    "spoofed-from@example.org",
                    "subject"
            )
    );

    verify(mailSender, never())
            .send(any(MimeMessage.class));
}
~~~

This is a pseudo-test using an `applicationService` with a sender allowlist policy, not a method on the example `OrderReceiptMailer`. Verify:

- From addresses come only from authorized configurations/identities;
- recipients are validated and checked for authorization;
- control characters are rejected in header values;
- secret data is never placed in headers;
- subjects and custom headers enforce reasonable length limits;
- message-preparation errors are never swallowed and followed by sending a half-built message.

### 18.1. Do not use verifyNoInteractions if createMimeMessage was already called

If the service constructs the message before validating, the mock `JavaMailSender` has already received a `createMimeMessage()` call. A test using:

~~~java
verifyNoInteractions(mailSender);
~~~

will fail even though `send(...)` was never called. If the goal is verifying **nothing was sent to transport**, the more focused assertion is:

~~~java
verify(mailSender, never())
        .send(any(MimeMessage.class));
~~~

If the architecture requires validation to happen **before creating MIME**, you can assert `createMimeMessage()` was not called; that is a stricter contract.

## 19. Mockito ArgumentCaptor and overload/varargs pitfalls

`JavaMailSender` has overloads for one or many messages. When capturing, target the exact signature production code uses.

Example sending one message:

~~~java
ArgumentCaptor<MimeMessage> captor =
        ArgumentCaptor.forClass(MimeMessage.class);

verify(mailSender).send(captor.capture());
~~~

If the service calls:

~~~java
mailSender.send(message1, message2);
~~~

the varargs/array signature differs; capture each argument or the array matching your Mockito version and overload. Never assume `getValue()` holds all messages from a batch.

If code uses:

~~~java
mailSender.send(mimeMessagePreparator);
~~~

the test must capture `MimeMessagePreparator` or stub `send(MimeMessagePreparator)` to execute the preparator on a real `MimeMessage`. Mockito does not automatically run callbacks/preparators passed into mocks.

### 19.1. Testing MimeMessagePreparator

Example service using:

~~~java
mailSender.send(mimeMessage -> {
    MimeMessageHelper helper =
            new MimeMessageHelper(mimeMessage, "UTF-8");
    helper.setTo("alice@example.net");
    helper.setSubject("Notification");
    helper.setText("Content");
});
~~~

When `JavaMailSender` is a mock, the callback **does not run automatically**. Use `doAnswer` to populate a real message:

~~~java
import org.springframework.mail.javamail.MimeMessagePreparator;

doAnswer(invocation -> {
    MimeMessagePreparator preparator =
            invocation.getArgument(0);
    MimeMessage realMessage = new MimeMessage(
            Session.getInstance(new Properties())
    );

    preparator.prepare(realMessage);
    capturedMessages.add(realMessage);
    return null;
}).when(mailSender)
  .send(any(MimeMessagePreparator.class));
~~~

`capturedMessages` is a `List<MimeMessage>` initialized by the test. After calling the service, inspect messages in the list and assert From/To/Subject just like in earlier examples.

Difference:

- `send(MimeMessage)`: the service typically prepared the message before calling the mock.
- `send(MimeMessagePreparator)`: the service passes a callback, so the mock must explicitly invoke it if the test wants to verify content.

Without running the preparator, the test only confirms the service passed a callback, not that the email inside it was built properly.

## 20. A combined header test example

Below is a test focused on key headers using the service and setup from the earlier sections.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

@Test
void preparesCorrectRecipientsSubjectAndHeaders()
        throws Exception {

    mailer.sendReceipt(
            "alice@example.net",
            "A123",
            "Đơn hàng A123 đã xác nhận.",
            "<p>Đơn hàng <strong>A123</strong> đã xác nhận.</p>"
    );

    ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);
    verify(mailSender, times(1)).send(captor.capture());

    MimeMessage actual = captor.getValue();

    assertEquals(
            "orders@notify.example.com",
            ((InternetAddress) actual.getFrom()[0]).getAddress()
    );
    assertEquals(
            "alice@example.net",
            ((InternetAddress) actual.getRecipients(
                    Message.RecipientType.TO)[0]).getAddress()
    );
    assertEquals(
            "finance@example.com",
            ((InternetAddress) actual.getRecipients(
                    Message.RecipientType.CC)[0]).getAddress()
    );
    assertEquals(
            "audit@example.com",
            ((InternetAddress) actual.getRecipients(
                    Message.RecipientType.BCC)[0]).getAddress()
    );
    assertEquals(
            "support@example.com",
            ((InternetAddress) actual.getReplyTo()[0]).getAddress()
    );
    assertNotNull(actual.getHeader("Reply-To"));
    assertEquals(
            "Xác nhận đơn hàng A123",
            actual.getSubject()
    );
    assertEquals(
            "order-receipt",
            actual.getHeader("X-Template-Id", null)
    );
    assertEquals(
            "ORDER_RECEIPT",
            actual.getHeader("X-Notification-Type", null)
    );
}
~~~

This test uses no network yet reads values stored by Jakarta Mail, catching bugs such as:

- From address mistakenly changed;
- missing Bcc/Reply-To;
- email sent to the wrong recipient;
- subject missing order number or suffering encoding bugs;
- template headers missing or having wrong values;
- service failing to call `send`.

If the application contract forbids Cc/Bcc, assert `null`/empty accordingly instead of reusing the fixture above.

## 21. Common anti-patterns

| Anti-pattern | Why it is bad | Replacement |
| --- | --- | --- |
| Only `verify(send(any()))` | Unknown if content/headers are right | ArgumentCaptor + typed MimeMessage getters |
| Mocking MimeMessage too | Getters do not reflect setters automatically | Use a real in-memory MimeMessage |
| Requiring SMTP test server in every unit test | Slow tests, extra dependencies | Mock JavaMailSender |
| Comparing raw Subject directly against Unicode | MIME encoded-words break the assertion | `getSubject()` |
| Asserting root `Content-Type=text/html` on multipart | Root is actually multipart | Traverse body parts |
| Hardcoding body part indices | Nested MIME structures vary | Recursive MIME traversal |
| Hardcoding boundaries and Message-IDs | Library generates them dynamically | Assert semantic/round-trip properties |
| Expecting Bcc absent on pre-send object | Bcc is still needed for envelope | Assert recipient; test transport separately |
| Treating `getReplyTo()` as proof Reply-To header exists | Can fall back to From | Also check the raw header |
| Asserting fixed raw Content-Transfer-Encoding | Valid encodings vary | Read decoded content |
| Treating normal return from mock `send` as SMTP success | Mock opens no network | Separate SMTP integration test |
| Asserting ESP-added DKIM-Signature in unit tests | Provider signs after submission | Test domain/provider/receiver |
| Forgetting to stub `createMimeMessage()` | Mock returns null | Return a real MimeMessage |
| Never running MimeMessagePreparator callback | No message gets built | `doAnswer` calling `prepare` |
| `saveChanges()` before every assertion | Can alter dynamic headers | Use only when testing serialization |
| Logging raw MIME containing real data | Leaks recipients/body/tokens | Dummy fixtures, minimal logging |

## 22. Checklist for writing MimeMessage unit tests

### Setup

- [ ] Mock `JavaMailSender`, never hit real SMTP.
- [ ] Stub `createMimeMessage()` to return a real `MimeMessage` with an in-memory `Session`.
- [ ] If using `MimeMessagePreparator`, make the mock execute the preparator cleanly.
- [ ] Do not start the entire Spring context when simple constructor injection suffices.

### Headers and recipients

- [ ] Verify exact From mailbox and display name if present.
- [ ] Verify To/Cc/Bcc via `getRecipients()`.
- [ ] Verify Reply-To; when needed, verify the header is actually present.
- [ ] Verify Unicode subjects via `getSubject()`.
- [ ] Verify custom headers via `getHeader()`.
- [ ] Verify no sensitive or policy-violating headers exist.

### MIME

- [ ] Verify plain text and HTML via MIME tree traversal.
- [ ] Do not hardcode body-part order unless required by contract.
- [ ] Verify charset and decoded content.
- [ ] Verify attachment filename/content type/bytes when part of contract.
- [ ] Verify inline CID and HTML references when present.

### Stability and boundaries

- [ ] Do not hardcode Date, Message-ID, boundaries, or raw header folding unnecessarily.
- [ ] Call `saveChanges()` only when testing serialization or library-generated headers.
- [ ] Test that invalid inputs do not call `send`.
- [ ] Do not treat unit tests as proof of SMTP/ESP delivery or DKIM/DMARC.
- [ ] Never use real user emails, secrets, or tokens in fixtures/logs.

## 23. Key points to remember

- **MimeMessage is a real data structure** that can be built and read entirely in memory without SMTP.
- **Mock JavaMailSender**, while keeping `MimeMessage` as a real object so Jakarta Mail setters/getters work.
- `ArgumentCaptor<MimeMessage>` captures the message passed by the service to `send`.
- Read From/To/Cc/Bcc/Reply-To via typed APIs; avoid parsing raw headers unnecessarily.
- `getSubject()` is ideal for asserting decoded Vietnamese subjects.
- `getHeader()` reads custom headers; watch for null values, multiple occurrences, and header folding.
- Root MIME may be `multipart/*`; plain/HTML bodies and attachments live inside nested parts.
- `saveChanges()` and `writeTo()` can generate/update headers such as Message-ID/Date/MIME metadata.
- **Bcc in a pre-send MimeMessage** does not mean Bcc will appear publicly in the delivered email.
- Tests with a mock sender prove **the prepared email structure**, not SMTP acceptance, delivery, or inbox placement.

When testing Spring Framework Mail, the most reliable and maintainable approach is **capturing a real `MimeMessage` and inspecting its semantics via the Jakarta Mail API**. That way, unit tests catch recipient, subject, header, charset, and MIME-part bugs while staying fast, needing no SMTP server, and remaining independent of dynamic bytes generated during message serialization.

### References

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper`, and sending MIME.
- **Spring Framework API — JavaMailSender:** `send(MimeMessage)` and `send(MimeMessagePreparator)` overloads.
- **Spring Framework API — MimeMessageHelper:** From/To/Cc/Bcc/Reply-To/Subject/Text setters and multipart modes.
- **Jakarta Mail API — MimeMessage:** `getFrom`, `getRecipients`, `getReplyTo`, `getSubject`, `getHeader`, `saveChanges`, `writeTo`.
- **Jakarta Mail API — Multipart, BodyPart, and Part:** MIME tree traversal, Content-Type, Content-ID, and attachments.
- **JUnit Jupiter User Guide:** unit test structure and assertions.
- **Mockito Documentation:** `ArgumentCaptor`, `verify`, `when`, `doAnswer`, and `MockitoExtension`.
- **RFC 5322 — Internet Message Format:** email headers, mailbox syntax, and message structure.
- **RFC 2045–2049 — MIME:** Content-Type, transfer encoding, charsets, encoded words, and multiparts.
- **RFC 2369 and RFC 8058:** `List-Unsubscribe` and one-click unsubscribe when testing marketing headers.
