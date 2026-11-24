# Avoiding Real Mail Server Dependencies in Unit Tests

A **Spring Framework Mail** application may use `JavaMailSender` to send account verification emails, invoices, alerts, or order notifications. When writing unit tests for these features, you should never require a running SMTP server, never use real email accounts, and never let tests accidentally send emails to real users.

A test that only needs to verify "the service built the right email and requested sending" requires no network connection. You can use **Mockito** to replace `JavaMailSender` with a mock, return a **real in-memory `MimeMessage`**, and then inspect recipient addresses, subject, plain-text/HTML content, attachments, and error handling. When using `SimpleMailMessage`, you can inspect the object passed to `MailSender` directly.

This lesson focuses on the principle of **avoiding real mail server dependencies in unit tests**, how to design test boundaries, JUnit 5/Mockito/AssertJ examples, MIME testing with Jakarta Mail, distinguishing unit tests from integration tests, and safeguards to protect CI environments from unintended side effects.

## 1. Why should unit tests not send real SMTP traffic?

Suppose a test invokes a service wired to a `JavaMailSenderImpl` configured from the environment:

```text
JUnit test
   |
   v
OrderService
   |
   v
NotificationService
   |
   v
JavaMailSenderImpl
   |
   | TCP / TLS / SMTP AUTH / DATA
   v
External SMTP provider
   |
   v
Recipient mailbox
```

The test outcome then depends on:
- whether the network can reach the SMTP host;
- DNS, firewalls, proxies, and TLS certificates;
- whether SMTP passwords or tokens are still valid;
- quotas/rate limits or provider health;
- relay response latency;
- recipient domains/addresses in test data;
- anti-spam policies and suppression lists.

A minor bug in email content can be masked by network failures. Conversely, a test can pass despite broken email content because SMTP accepts the message without validating business facts.

**Unit tests must be fast, isolated, repeatable, and free of external side effects.** They test logic controlled by the development team rather than making availability of a third-party SMTP system a prerequisite for success.

## 2. Where should test boundaries sit?

With Spring Mail, a testable architecture looks like:

```text
Business use case
      |
      v
Notification / mail application service
      |
      +--> Validate recipient and business data
      |
      +--> Render subject/plain/HTML
      |
      +--> Build MimeMessage
      |
      v
JavaMailSender interface     <-- replace with Mockito mock
      |
      v
JavaMailSenderImpl           <-- used only in integration
      |
      v
SMTP server
```

Distinguish:
- **Renderer unit test:** verifies text and HTML strings from business data.
- **Service unit test:** verifies which message is sent, who receives it, when it is sent, and how errors are handled.
- **MIME construction test:** uses real in-memory Jakarta Mail to verify MIME parts, charsets, headers, and attachments.
- **SMTP integration test:** verifies connecting to an SMTP sandbox/test server, STARTTLS, AUTH, and protocol behavior.
- **End-to-end test:** verifies provider acceptance and test-mailbox delivery.

The first three layers require no real SMTP server.

| Question | Unit test | SMTP integration/E2E |
|---|---|---|
| Was `send` called exactly once? | Yes, with Mockito | Not required |
| Are `To`, `Subject`, and `From` right? | Yes, capture/inspect message | Can verify additionally |
| Do plain text and HTML have right facts? | Yes | Can verify additionally |
| Are attachment names/contents right? | Yes, using in-memory MIME | Can verify additionally |
| Any side effects when data is invalid? | Yes, verify sender not called | Not needed |
| Do SMTP credentials and TLS work? | No | Yes |
| Does relay/provider accept `DATA`? | No | Yes |
| Do SPF/DKIM/DMARC pass? | No | Requires real sending/receiving path |
| Does mail land in Inbox or Spam? | No | E2E/live observation |

**Never claim "the email was delivered" merely because a unit test verified `send(...)` was called.**

## 3. JavaMailSender is the right substitution seam

Spring provides key abstractions:

- `MailSender`: sends `SimpleMailMessage`, suited for simple plain-text emails.
- `JavaMailSender`: extends `MailSender`, able to create and send `MimeMessage` as well as send via `MimeMessagePreparator`.
- `JavaMailSenderImpl`: implementation using Jakarta Mail SMTP transport that can connect to a real server.

A service should depend on the **interface**:

```java
@Service
public class NotificationService {
    private final JavaMailSender mailSender;

    public NotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
```

Never instantiate a real sender inside a method:

```java
// Unfavorable for unit tests:
public void sendMail() {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("smtp.example.com");
    // ...
    sender.send(message);
}
```

The second approach creates a hidden dependency: tests cannot easily swap it out with a mock. Constructor injection makes dependencies explicit, controllable, and avoids configuring SMTP settings in unit tests.

## 4. Testing tools and dependencies

In a Spring Boot application using Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` typically supplies JUnit Jupiter, Mockito, AssertJ, and Spring test utilities through the project version's dependency management.

Examples in this lesson use:
- Spring Framework 6+/Spring Boot 3+, hence `jakarta.mail.*` instead of legacy `javax.mail.*` packages;
- Java 17+ for records and text blocks;
- JUnit 5 for running assertions;
- Mockito to substitute the sender;
- AssertJ for readable data assertions.

**No Docker SMTP service, username/password, or Internet connection is needed** for these unit test examples.

### 4.1. Starting a Spring ApplicationContext is unnecessary

For a service with simple constructor injection, unit tests can construct it directly with `new`:

```java
JavaMailSender sender = mock(JavaMailSender.class);
NotificationService service = new NotificationService(sender);
```

This is a small test requiring no `@SpringBootTest`. Use a Spring test context only when the behavior under test directly involves dependency wiring/configuration or framework integration.

### 4.2. @Mock, @InjectMocks, and @MockitoBean differ

| Tool | Scope | When to use |
|---|---|---|
| `Mockito.mock(...)` | Plain JUnit test | When constructing mocks explicitly. |
| `@Mock` + `MockitoExtension` | Plain JUnit test | When letting Mockito initialize mocks via annotations. |
| `@InjectMocks` | Plain JUnit test | Constructor/field injection into the test target when appropriate. |
| `@MockitoBean` | Spring test `ApplicationContext` in supporting Spring versions | Replacing a bean in Spring context to test wiring/use cases. |
| `@MockBean` | Older Spring Boot versions | Bean replacement in projects using that API; watch for version deprecations. |

Do not make `@SpringBootTest` + mock sender the default for every unit test, because booting the context is slower and pulls irrelevant components into the test.

## 5. Simplest case: SimpleMailMessage

If an email has only subject and plain text, `SimpleMailMessage` is usually enough.

### 5.1. Service under test

```java
package com.example.mail;

import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

public class WelcomeMailService {

    private final MailSender sender;

    public WelcomeMailService(MailSender sender) {
        this.sender = sender;
    }

    public void sendWelcome(String to, String displayName) {
        SimpleMailMessage message = new SimpleMailMessage();

        message.setFrom("no-reply@example.com");
        message.setTo(to);
        message.setSubject("Welcome " + displayName);
        message.setText(
            "Hello " + displayName + ",\n"
                + "Your account has been created successfully."
        );

        sender.send(message);
    }
}
```

`SimpleMailMessage` does not support HTML parts, inline images, or MIME attachments the way `MimeMessage` does. Do not use it when an email needs multiple MIME representations.

### 5.2. Unit test completely free of SMTP

```java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;

class WelcomeMailServiceTest {

    @Test
    void sendsExpectedPlainText() {
        MailSender sender = mock(MailSender.class);
        WelcomeMailService service =
            new WelcomeMailService(sender);

        service.sendWelcome(
            "customer@example.net",
            "Nguyễn Thị Ánh"
        );

        ArgumentCaptor<SimpleMailMessage> captor =
            ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender).send(captor.capture());

        SimpleMailMessage actual = captor.getValue();

        assertThat(actual.getFrom())
            .isEqualTo("no-reply@example.com");

        assertThat(actual.getTo())
            .containsExactly("customer@example.net");

        assertThat(actual.getSubject())
            .isEqualTo("Welcome Nguyễn Thị Ánh");

        assertThat(actual.getText())
            .contains("Hello Nguyễn Thị Ánh")
            .contains("Your account has been created");
    }
}
```

Here Mockito only **records the call**. There are no sockets, SMTP AUTH, real email sending, or mail server environment.

### 5.3. Why not only verify send was called?

Too weak of a test:

```java
verify(sender).send(any(SimpleMailMessage.class));
```

It passes even if the subject is empty, the To address is swapped, or the body is wrong. When the business behavior is "send a welcome email to the right person with the right details," capture and assert the important fields.

## 6. How does MimeMessage differ from SimpleMailMessage?

Emails with HTML, plain + HTML, inline images, or file attachments usually use `MimeMessage` together with `MimeMessageHelper`.

Service example:

```java
MimeMessage message = sender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("orders@example.com");
helper.setTo(recipient);
helper.setSubject("Order ORD-001 confirmation");
helper.setText(plainText, htmlText);

sender.send(message);
```

Unit-test hurdle: calling `JavaMailSender.createMimeMessage()` on an unstubbed Mockito mock returns `null`. Receiving null causes `MimeMessageHelper` to fail before reaching send.

The solution is **mocking the sender while using a real in-memory `MimeMessage`**.

## 7. Create an in-memory MimeMessage without a server

Jakarta Mail provides `Session` for creating and managing MIME messages. Merely creating a `Session` and `MimeMessage` **never connects to SMTP**:

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.util.Properties;

Session session = Session.getInstance(new Properties());
MimeMessage message = new MimeMessage(session);
```

No SMTP host, port, or credentials are needed in `Properties`.

`Session` here is Jakarta Mail configuration and state associated with the message; **it is not an active SMTP TCP session**. Network connections happen only when invoking real transport operations, such as sending via `JavaMailSenderImpl`.

### 7.1. Stub createMimeMessage on the mock sender

```java
JavaMailSender sender = mock(JavaMailSender.class);

MimeMessage inMemory = new MimeMessage(
    Session.getInstance(new Properties())
);

when(sender.createMimeMessage())
    .thenReturn(inMemory);
```

When the service calls `sender.createMimeMessage()`, it gets a real message to populate that can be inspected afterward. When it calls `sender.send(message)`, Mockito **sends nowhere**.

### 7.2. Why not mock MimeMessage as well?

You could mock `MimeMessage`, yet methods like `setRecipients`, `getContent`, `setText`, `saveChanges`, and MIME multiparts would have no real behavior unless tests manually stubbed every step.

When the goal is verifying **the message was built properly**, a real in-memory `MimeMessage` is far more reliable and simpler. Mock the **I/O boundary**, not every data object.

## 8. Testable Spring Mail service example

### 8.1. Email model and content

```java
package com.example.mail;

public record OrderMailData(
    String customerName,
    String orderId,
    String orderUrl,
    String amountText
) {}

public record RenderedMail(
    String plain,
    String html
) {}
```

Create a simple renderer:

```java
package com.example.mail;

public class OrderMailRenderer {

    public RenderedMail render(OrderMailData data) {
        String plain = """
            Hello %s,

            Order %s has been confirmed.
            Total amount: %s

            View order:
            %s
            """.formatted(
                data.customerName(),
                data.orderId(),
                data.amountText(),
                data.orderUrl()
            );

        // Illustrates a static HTML renderer; when accepting
        // untrusted data, use a template engine escaping
        // appropriately for text and URL attribute contexts.
        String html = """
            <html><body>
              <h1>Order confirmation</h1>
              <p>Your order has been confirmed.</p>
              <p>See full details in the matching text version.</p>
            </body></html>
            """;

        return new RenderedMail(plain, html);
    }
}
```

This example shows decoupling the renderer from the sender. In a real product, **both plain and HTML must include key business details**, sharing one view model to avoid discrepancies. A real HTML renderer should include order code, amount, and link in the template with proper escaping.

### 8.2. Service knowing only the JavaMailSender abstraction

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class OrderMailService {

    private final JavaMailSender sender;
    private final OrderMailRenderer renderer;

    public OrderMailService(
            JavaMailSender sender,
            OrderMailRenderer renderer) {
        this.sender = sender;
        this.renderer = renderer;
    }

    public void send(String recipient, OrderMailData data)
            throws MessagingException {

        RenderedMail content = renderer.render(data);

        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("orders@example.com");
        helper.setTo(recipient);
        helper.setSubject(
            "Order confirmation " + data.orderId()
        );
        helper.setText(content.plain(), content.html());

        sender.send(message);
    }
}
```

There is no `JavaMailSenderImpl` inside the service. Swapping the sender with a mock requires zero changes to production code.

## 9. Mockito unit test capturing MimeMessage

```java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

import java.util.Properties;

class OrderMailServiceTest {

    @Test
    void preparesAndRequestsExpectedMessage()
            throws Exception {

        JavaMailSender sender = mock(JavaMailSender.class);
        MimeMessage message = new MimeMessage(
            Session.getInstance(new Properties())
        );

        when(sender.createMimeMessage()).thenReturn(message);

        OrderMailService service = new OrderMailService(
            sender,
            new OrderMailRenderer()
        );

        OrderMailData order = new OrderMailData(
            "Nguyễn Thị Ánh",
            "ORD-2026-001",
            "https://shop.example.com/orders/ORD-2026-001",
            "450.000 ₫"
        );

        service.send("customer@example.net", order);

        ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender).send(captor.capture());

        MimeMessage sent = captor.getValue();
        sent.saveChanges();

        assertThat(sent.getSubject())
            .isEqualTo("Order confirmation ORD-2026-001");

        assertThat(
            ((InternetAddress) sent.getFrom()[0]).getAddress()
        ).isEqualTo("orders@example.com");

        assertThat(
            ((InternetAddress) sent.getAllRecipients()[0]).getAddress()
        ).isEqualTo("customer@example.net");
    }
}
```

Key takeaways:
- `JavaMailSender` is a mock.
- `MimeMessage` is a real Jakarta Mail object **living in memory**.
- `send(...)` never executes through `JavaMailSenderImpl`.
- Email data is verified without SMTP side effects.

### 9.1. Capture arguments instead of verifying a generic boolean

If the service sends two emails or invokes the sender multiple times, distinguish messages by business ID, recipient, or message key. Never check only the invocation count and assume all messages are right.

### 9.2. Never keep a mutable object and mutate it after sending

`MimeMessage` is mutable. If production code reuses the same instance across recipients or sends, a test captor will see the final mutated state, masking bugs.

Best practice is creating **a separate `MimeMessage` per logical email/send**, never shared across threads. When an exact snapshot is needed, serialize the message inside a test stub/answer at `send` time and re-parse it for inspection.

## 10. Verify plain text and HTML inside the MIME tree

With `helper.setText(plain, html)`, `MimeMessage` usually contains `multipart/alternative`, potentially nested inside `multipart/mixed` and `multipart/related` depending on multipart mode.

```text
MimeMessage
  |
  +-- multipart/mixed
       |
       +-- multipart/related
            |
            +-- multipart/alternative
                 |
                 +-- text/plain; charset=UTF-8
                 |
                 +-- text/html; charset=UTF-8
```

The exact structure depends on how the message is built. Never assume `message.getContent()` is a `String` or that the plain part always sits directly at the root.

### 10.1. Recursive MIME-part finder helper

```java
package com.example.mail;

import jakarta.mail.Multipart;
import jakarta.mail.Part;

import java.util.ArrayList;
import java.util.List;

public final class MimePartFinder {

    private MimePartFinder() {}

    public static List<Part> find(
            Part root,
            String mimeType) throws Exception {

        List<Part> matches = new ArrayList<>();
        visit(root, mimeType, matches);
        return matches;
    }

    private static void visit(
            Part part,
            String mimeType,
            List<Part> matches) throws Exception {

        if (part.isMimeType(mimeType)) {
            matches.add(part);
            return;
        }

        Object content = part.getContent();

        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                visit(multipart.getBodyPart(i), mimeType, matches);
            }
        }
    }
}
```

This helper fits standard MIME multiparts in this lesson. When a system handles forwarded `message/rfc822` or `text/plain` attachments, filter by `Content-Disposition` or scope to the main **body** to avoid mistaking an attachment part for the plain fallback.

### 10.2. Test both plain and HTML without SMTP

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.util.List;
import java.util.Properties;

class MimeBodyUnitTest {

    @Test
    void containsBothBodyAlternatives() throws Exception {
        MimeMessage message = new MimeMessage(
            Session.getInstance(new Properties())
        );

        MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");

        String plain =
            "Xin chào Nguyễn Thị Ánh,\nTổng tiền: 450.000 ₫";
        String html =
            "<html><body><p>Xin chào Nguyễn Thị Ánh</p>"
                + "<p>Tổng tiền: 450.000 ₫</p></body></html>";

        helper.setText(plain, html);
        message.saveChanges();

        List<Part> plainParts =
            MimePartFinder.find(message, "text/plain");
        List<Part> htmlParts =
            MimePartFinder.find(message, "text/html");

        assertThat(plainParts).hasSize(1);
        assertThat(htmlParts).hasSize(1);

        assertThat((String) plainParts.get(0).getContent())
            .isEqualTo(plain);

        assertThat((String) htmlParts.get(0).getContent())
            .isEqualTo(html);
    }
}
```

This test calls no sender and needs no SMTP host. It verifies Spring/Jakarta Mail's MIME body construction.

### 10.3. Test charset instead of coupling to transfer encoding

You can inspect `Content-Type`:

```java
import jakarta.mail.internet.ContentType;

Part plainPart =
    MimePartFinder.find(message, "text/plain").get(0);

ContentType type =
    new ContentType(plainPart.getContentType());

assertThat(type.getBaseType())
    .isEqualToIgnoringCase("text/plain");

assertThat(type.getParameter("charset"))
    .isEqualToIgnoringCase("UTF-8");
```

Never demand that raw MIME always use a fixed Base64 or quoted-printable encoding. Both are valid whenever Jakarta Mail decodes the exact original content.

## 11. Serialize and re-parse MIME for deeper verification

An in-memory `MimeMessage` can be written to raw MIME bytes and re-parsed by Jakarta Mail **without a network**:

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Properties;

Session session = Session.getInstance(new Properties());
MimeMessage original = new MimeMessage(session);

// Populate headers and body via MimeMessageHelper.
MimeMessageHelper helper =
    new MimeMessageHelper(original, false, "UTF-8");
helper.setSubject("Hóa đơn của Ánh 🎉");
helper.setText("Tổng tiền: 450.000 ₫", false);

original.saveChanges();

ByteArrayOutputStream bytes = new ByteArrayOutputStream();
original.writeTo(bytes);

MimeMessage decoded = new MimeMessage(
    session,
    new ByteArrayInputStream(bytes.toByteArray())
);
```

Assertions:

```java
assertThat(decoded.getSubject())
    .isEqualTo("Hóa đơn của Ánh 🎉");

assertThat(decoded.isMimeType("text/plain")).isTrue();

assertThat((String) decoded.getContent())
    .isEqualTo("Tổng tiền: 450.000 ₫");
```

This verifies both serialization and decoding at the MIME layer while still avoiding SMTP. For multi-part messages, use a MIME-tree traversal helper instead of casting `getContent()` to `String`.

### 11.1. Never confuse raw MIME with decoded content

Raw MIME may contain:

```text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: base64
```

Then `"Tổng tiền: 450.000 ₫"` will not appear as readable literal UTF-8 inside the raw source. Tests should read `getContent()` after parsing instead of searching for literal Vietnamese text inside transfer-encoded raw bytes.

### 11.2. Never hardcode Message-ID and MIME boundaries

`saveChanges()` may generate `Message-ID`, `Date`, boundaries, and headers. These values can vary by library version, timestamp, and environment.

Content unit tests should not compare the entire raw MIME byte-for-byte unless explicitly testing a serialization contract. Assert semantic properties: sender, recipients, subject, part types, body, and attachments.

## 12. Test attachments without real files or SMTP

An email carrying a PDF invoice or report can be tested with **in-memory resources**. In Spring, `ByteArrayResource` works well when payloads are small and created right inside the test.

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

import java.nio.charset.StandardCharsets;
import java.util.Properties;

MimeMessage message = new MimeMessage(
    Session.getInstance(new Properties())
);

MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("customer@example.net");
helper.setSubject("November invoice");
helper.setText(
    "The invoice is attached to this email.",
    "<p>The invoice is attached to this email.</p>"
);

byte[] attachmentBytes =
    "invoice,amount\nINV-001,450000\n"
        .getBytes(StandardCharsets.UTF_8);

helper.addAttachment(
    "invoice.csv",
    new ByteArrayResource(attachmentBytes),
    "text/csv; charset=UTF-8"
);

message.saveChanges();
```

The CSV content is dummy data only. Never use real invoices or documents containing real customer details in unit tests.

### 12.1. Locate attachments by disposition

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.util.ArrayList;
import java.util.List;

static void findAttachments(Part part, List<Part> result)
        throws Exception {

    String disposition = part.getDisposition();

    if (Part.ATTACHMENT.equalsIgnoreCase(disposition)) {
        result.add(part);
        return;
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            findAttachments(multipart.getBodyPart(i), result);
        }
    }
}
```

Then:

```java
List<Part> attachments = new ArrayList<>();
findAttachments(message, attachments);

assertThat(attachments).hasSize(1);
assertThat(attachments.get(0).getFileName())
    .isEqualTo("invoice.csv");
```

In practice, some MIME parts carry a filename yet have a missing or nonstandard disposition; if your application parses external inbound emails, use a more general parser. For messages built by your own service, this test suffices to illustrate checking declared attachments.

### 12.2. Never use a single-use InputStream and ignore its lifecycle

`MimeMessageHelper.addAttachment(...)` and `addInline(...)` may need to re-open the resource stream during processing. `ByteArrayResource` can open multiple fresh streams from its byte array. An `InputStreamResource` wrapping a single-use stream may fail in certain MIME-building flows. Test with re-readable resources to prevent hard-to-reproduce sending bugs.

## 13. Test inline images without sending real emails

If HTML contains:

```html
<img src="cid:brand-logo" alt="Store logo">
```

You can verify:
- HTML contains the `cid:brand-logo` reference;
- MIME contains an image part with the matching `Content-ID`;
- the plain-text fallback does not depend on the image;
- the resource is added in the right order after `setText`.

Example:

```java
MimeMessage message = new MimeMessage(
    Session.getInstance(new Properties())
);

MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");

String plain = "Notification from Example Store.";
String html =
    "<html><body><img src=\"cid:brand-logo\" alt=\"Logo\">"
        + "<p>Notification from Example Store.</p></body></html>";

helper.setText(plain, html);

byte[] smallPngBytes = loadTestPngBytes();

helper.addInline(
    "brand-logo",
    new ByteArrayResource(smallPngBytes),
    "image/png"
);
```

`loadTestPngBytes()` is a test-defined fixture helper and should return a valid PNG when testing image contents. When testing only MIME relationships, bytes can be fixture-controlled with no network calls.

**Testing MIME with unit tests alone does not prove every mail client will display CID images**, because client behavior and image policies fall under compatibility testing.

## 14. Test that sender is not called when data is invalid

Unit tests can verify the cases where a service must **reject before sending**.

Service example:

```java
public void sendToVerifiedRecipient(
        String recipient,
        boolean verified,
        String content) {

    if (!verified) {
        throw new IllegalArgumentException(
            "Recipient must be verified"
        );
    }

    SimpleMailMessage message = new SimpleMailMessage();
    message.setFrom("security@example.com");
    message.setTo(recipient);
    message.setSubject("Security notice");
    message.setText(content);

    sender.send(message);
}
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void doesNotSendToUnverifiedRecipient() {
    MailSender sender = mock(MailSender.class);
    SecurityMailService service = new SecurityMailService(sender);

    assertThatThrownBy(() ->
        service.sendToVerifiedRecipient(
            "unverified@example.net",
            false,
            "Notice"
        )
    ).isInstanceOf(IllegalArgumentException.class);

    verifyNoInteractions(sender);
}
```

`SecurityMailService` is an illustrative class holding that method. In a real system, recipient verification and authorization must be enforced in the appropriate service/repository. This test simply guarantees **no send invocation occurs** on the rejected branch.

Similar cases to test:
- unauthorized to send for the given order;
- recipient address disallowed by business policy;
- user unsubscribed from marketing;
- duplicate send request blocked by an idempotency guard;
- template data missing a required field.

Never use a mock sender to argue that input validation is "safe"; recipient and domain validation are separate logic that must be tested directly.

## 15. Test MailException handling without real network errors

To verify how a service reacts when sending fails, there is no need to block firewalls or take an SMTP provider offline. Configure the mock to throw an exception.

### 15.1. Simulated MailSendException

```java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSender;

JavaMailSender sender = mock(JavaMailSender.class);

doThrow(new MailSendException("Simulated send failure"))
    .when(sender)
    .send(any(MimeMessage.class));
```

This is an **intentionally simulated exception**, not a real SMTP reply. The service may record an error status, rethrow the exception, or return an outcome per contract.

### 15.2. Verify the service handles failures per policy

Suppose a service is designed as:

```java
public enum SubmissionStatus {
    ACCEPTED,
    FAILED
}

public SubmissionStatus sendAndReport(MimeMessage message) {
    try {
        sender.send(message);
        return SubmissionStatus.ACCEPTED;
    } catch (MailException ex) {
        return SubmissionStatus.FAILED;
    }
}
```

A test can assert:

```java
@Test
void reportsFailureWhenSenderThrows() {
    JavaMailSender sender = mock(JavaMailSender.class);

    doThrow(new MailSendException("Test failure"))
        .when(sender)
        .send(any(MimeMessage.class));

    SubmissionService service = new SubmissionService(sender);

    MimeMessage message = new MimeMessage(
        Session.getInstance(new Properties())
    );

    assertThat(service.sendAndReport(message))
        .isEqualTo(SubmissionStatus.FAILED);
}
```

`SubmissionService` is an illustrative class wrapping the logic above. The status `ACCEPTED` in the example means only that `send` completed without synchronous error—not that the email was delivered or opened.

### 15.3. Be careful not to assume every failure was definitely unsent

SMTP has **ambiguous-outcome** scenarios, such as the relay accepting `DATA` while the network drops before the client receives the response. If a production system has an outbox/retry mechanism, unit tests must verify error classification instead of assuming every exception means a definitive `FAILED`.

A policy may classify:
- validation/preparation errors: never retry the same input as-is;
- transient errors clearly occurring before submission: retry with backoff;
- unknown outcome as to whether SMTP accepted the message: `UNKNOWN`, requiring reconciliation;
- authentication/configuration errors: never hammer with retries.

Unit tests can pass simulated exceptions or outcomes into a **pure classifier** and assert its decision. No real network outage is needed to test state transitions.

## 16. Test idempotency, outbox, and queue workers without SMTP

Critical mail-sending applications rarely call SMTP directly inside an HTTP request; instead they insert an outbox job and let a background worker send it.

```text
HTTP request
    |
    v
Application service
    |
    | insert email_outbox(messageKey, PENDING)
    v
Database / queue
    |
    v
Worker
    |
    | JavaMailSender.send(...)
    v
SMTP provider
```

Unit tests should verify:
1. A valid business request creates exactly one outbox item.
2. A request with the same idempotency key does not create a second item.
3. The worker only sends jobs it successfully claimed.
4. A `PENDING` job transitions to the right state.
5. When the sender throws an exception, the retry policy runs and state is persisted.
6. Zero real SMTP requests are made.

### 16.1. Worker example mocking repository and sender

```java
public class OutboxWorker {

    private final OutboxRepository repository;
    private final JavaMailSender sender;

    public OutboxWorker(
            OutboxRepository repository,
            JavaMailSender sender) {
        this.repository = repository;
        this.sender = sender;
    }

    public void process(OutboxJob job, MimeMessage mimeMessage) {
        sender.send(mimeMessage);
        repository.markAccepted(job.messageKey());
    }
}
```

Test:

```java
@Test
void marksAcceptedAfterSendReturns() {
    OutboxRepository repository = mock(OutboxRepository.class);
    JavaMailSender sender = mock(JavaMailSender.class);

    OutboxWorker worker = new OutboxWorker(repository, sender);

    OutboxJob job = new OutboxJob("msg-001");
    MimeMessage mime = new MimeMessage(
        Session.getInstance(new Properties())
    );

    worker.process(job, mime);

    InOrder calls = inOrder(sender, repository);
    calls.verify(sender).send(mime);
    calls.verify(repository).markAccepted("msg-001");
}
```

Requires importing `org.mockito.InOrder`, `Mockito.inOrder`, and your application's repository/job classes. `OutboxJob` in the example is a minimal model exposing `messageKey()`, not a Spring-provided class.

This test verifies **call ordering in code**, not outbox transactions or SMTP delivery. Guarantees around locking, concurrency, database transactions, and broker acks require integration tests against the corresponding infrastructure.

### 16.2. Avoid slow real-time retry delays in unit tests

If a worker uses exponential backoff, never make JUnit sleep 2, 4, 8, and 16 seconds before asserting. Instead:
- test `RetryPolicy` as a pure function returning delay/`nextAttemptAt`;
- inject a controllable `Clock` or scheduler;
- mock the repository/scheduler;
- verify scheduled attempt counts without waiting on wall-clock time;
- test retry budget limits and the `UNKNOWN` state.

Never write unit tests coupled to exact JVM scheduler timing or CI CPU speed.

## 17. When services use MimeMessagePreparator

`JavaMailSender` also has an overload accepting `MimeMessagePreparator`, letting the application supply a message-preparation callback.

Production example:

```java
public void sendReceipt(String recipient, String text) {
    sender.send(mime -> {
        MimeMessageHelper helper =
            new MimeMessageHelper(mime, false, "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Your invoice");
        helper.setText(text, false);
    });
}
```

If you merely mock `sender.send(preparator)`, the callback **never runs on its own**, so the test cannot inspect the prepared email.

### 17.1. Use Mockito Answer to run the preparator on an in-memory message

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;

import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessagePreparator;

import java.util.Properties;
import java.util.concurrent.atomic.AtomicReference;

JavaMailSender sender = mock(JavaMailSender.class);
AtomicReference<MimeMessage> captured = new AtomicReference<>();

doAnswer(invocation -> {
    MimeMessagePreparator preparator = invocation.getArgument(0);

    MimeMessage mime = new MimeMessage(
        Session.getInstance(new Properties())
    );

    preparator.prepare(mime);
    mime.saveChanges();
    captured.set(mime);
    return null;
}).when(sender).send(any(MimeMessagePreparator.class));

// Invoke the real service using the mock sender.
service.sendReceipt(
    "customer@example.net",
    "Xin chào Nguyễn Thị Ánh."
);

assertThat(captured.get()).isNotNull();
assertThat(captured.get().getSubject())
    .isEqualTo("Your invoice");
assertThat((String) captured.get().getContent())
    .contains("Nguyễn Thị Ánh");
```

In the example, `service` is an instance exposing `sendReceipt` configured with the mock `sender`. `doAnswer` runs the preparator in memory without forwarding to SMTP.

### 17.2. Never accidentally call real transport inside Answer

Only call `prepare(mime)`, `saveChanges`, and inspect MIME. Never call `Transport.send(mime)` or instantiate `JavaMailSenderImpl` to "simulate sending," as that re-opens the network boundary the test meant to isolate.

## 18. Should you write a FakeJavaMailSender instead of Mockito?

Not every test needs Mockito. When many tests inspect requested emails, an **in-memory fake sender** can be convenient. A fake can record sent messages at the API level without sending real SMTP traffic.

Conceptual diagram:

```text
Production:
MailService -> JavaMailSenderImpl -> SMTP

Unit tests:
MailService -> InMemoryMailSender -> captured messages
```

A fake should meet a minimal contract:
- `createMimeMessage()` returns a valid message.
- `send(...)` only records, never opens sockets.
- Each message stores a snapshot if code might mutate messages post-send.
- Provides a way to reset between tests.
- Does not silently "succeed" on unsupported overloads when that would mask bugs; throw `UnsupportedOperationException` for unused ones.

Mockito is usually better when:
- you need to verify exact call counts and ordering;
- you want to simulate `MailSendException`;
- the service has few test cases;
- you prefer not to maintain a full `JavaMailSender` implementation.

A fake helps when:
- many tests read the list of emails emitted by a use case;
- the team wants a DSL like `sentEmails()`;
- snapshot and overload contracts are agreed upon.

### 18.1. Do not rely on spy on a real sender for "safety"

`spy(new JavaMailSenderImpl())` **does not guarantee** blocking network calls. If any call goes unstubbed, the spy can invoke the real implementation and talk to SMTP. When the goal is zero mail-server dependencies, prefer a pure mock or an explicitly designed in-memory fake.

### 18.2. Is an embedded SMTP server a unit test?

In-process or containerized SMTP sandboxes are very valuable for testing the protocol. Yet once a service speaks SMTP/TCP—even to `localhost`—that is usually an **integration test** of network protocol and SMTP transport, not an isolated unit test like Mockito.

There is nothing wrong with embedded/test SMTP; place it in the right test suite instead of requiring it for every unit test.

## 19. Prevent tests from accidentally sending real emails

Never simply trust "CI probably has no SMTP credentials." A developer laptop or CI agent might accidentally hold real environment variables.

Key safeguards:
- Use constructor injection for the sender.
- Unit tests always use a mock/fake sender.
- Never call `JavaMailSenderImpl.send` in unit tests.
- Never put real recipients in fixtures; use example domains like `example.com` and `example.net`.
- Never copy real API keys, SMTP passwords, or tokens into test sources.
- Strictly separate `test` config from `dev/staging/production`.
- Never auto-start scheduled email-sending jobs in tests that do not need them.
- Restrict outbound network egress in test environments where infrastructure permits.
- Integration tests use authorized provider sandboxes or test SMTP servers.

### 19.1. When a Spring context auto-configures a real sender

A test with `@SpringBootTest` and the mail starter can create a real sender bean if matching properties are present. Creating the bean itself might not open a socket, yet:
- another bean might send mail on startup;
- an application event listener might send during context startup;
- a scheduled job might fire;
- `spring.mail.test-connection=true` can probe the connection at startup.

Therefore, for **unit tests**, avoid starting a full context unnecessarily. For Spring context tests, replace the sender with a test double and disable out-of-scope side-effect sources.

### 19.2. A test profile is not the sole line of defense

Suppose you have:

```yaml
# application-test.yml (illustrative)
spring:
  mail:
    host: localhost
    port: 2525
```

If the service calls real send without a server on `localhost:2525`, the test still fails with connection refused. If another process happens to listen on that port, the test can trigger unintended side effects. **Changing the host is not mocking.**

Unit tests should not hit any SMTP port at all.

### 19.3. Control @Async and @Scheduled

If the application sends email via `@Async` or a scheduler:
- unit tests call worker/service logic directly rather than relying on real thread pools;
- inject executors/schedulers or separate sending logic from async entry points;
- disable schedulers in test contexts that do not need them;
- never let tests finish before sending jobs complete;
- test concurrent scheduling only in a dedicated suite with explicit synchronization.

Annotating a method with `@Async` does not guarantee tests call it through a Spring proxy or actually test asynchronous behavior. Do not over-claim from a plain Java unit test calling the method directly.

## 20. Design deterministic, maintainable tests

### 20.1. Keep fixtures fixed

Example test data:

```text
Recipient: customer@example.net
Customer: Nguyễn Thị Ánh
Order ID: ORD-2026-001
Amount: 450.000 ₫
Action URL: https://shop.example.com/orders/ORD-2026-001
```

Pick dummy IDs, dummy URLs, and non-sensitive data. When timestamps are needed, use `Clock.fixed(...)` instead of `Instant.now()` in renderers/business logic. When locales are needed, pass `Locale.forLanguageTag("vi-VN")` instead of relying on the machine default locale.

### 20.2. Do not assert random MIME details

Avoid asserting directly on:
- boundary strings;
- library-generated Message-IDs;
- wall-clock `Date` headers;
- insignificant header ordering;
- fixed raw `Content-Transfer-Encoding`;
- exact multipart nesting depth when the API promises only plain/HTML.

Prefer asserting:
- decoded subject and body;
- MIME types and charsets;
- recipients;
- attachment filenames;
- action URLs and business facts.

### 20.3. Test exceptions and retries at the right layer

Unit tests for `MailRetryPolicy` can take a `FailureCategory` supplied by a classifier and return:
- `RETRY_AFTER`;
- `FAILED_PERMANENT`;
- `UNKNOWN_REQUIRES_RECONCILIATION`.

There is no need to reproduce a real TLS handshake or real SMTP timeout. Protocol-specific conditions belong in integration/contract tests.

### 20.4. Avoid cross-test dependencies

Each test should create its own mock sender, message, and fixture. Never share a static mutable `MimeMessage` across tests; never let test A mutate test B's message. With a stateful fake sender storing a list, reset state on every test.

## 21. Common bugs

| Symptom | Root cause | Fix |
|---|---|---|
| Test needs network and SMTP credentials | Service uses real `JavaMailSenderImpl` | Inject `JavaMailSender` and replace with mock. |
| `NullPointerException` in `MimeMessageHelper` | Default mock `createMimeMessage()` returns null | Stub to return a real in-memory `MimeMessage`. |
| Test passes despite wrong address | Only verified `send(any())` | Capture and inspect `To`/`From`. |
| Test passes despite broken body | Did not inspect MIME parts | Traverse plain/HTML and assert decoded content. |
| Test fails missing localhost SMTP | Changed host to localhost yet still ran real transport | Mock sender or move to SMTP integration tests. |
| Tests run slowly/flakily | Used `@SpringBootTest`, queues/schedulers, and network everywhere | Keep unit tests plain Java, mock I/O. |
| Unicode encoding test fails | Wrong charset, normalization, or raw MIME parsing | Use UTF-8 and decoded MIME assertions. |
| Test breaks on boundary values | Asserted raw MIME verbatim | Assert MIME semantics. |
| `MimeMessagePreparator` builds no content in test | Mocked `send` callback without running preparator | Use Mockito Answer to call `prepare` on in-memory message. |
| Test hits real SMTP despite using spy | Spy invokes real methods unless stubbed | Use a pure mock or fake. |
| Test emails real customers | Real fixtures/credentials used | Dummy domains and network-free sender. |
| Race condition in tests | Async/schedulers running outside unit-test scope | Isolate worker; test concurrency separately. |
| Email fails yet test marks "delivered" | Confused send invocation with provider delivery | Track status per contract; use integration/events for delivery. |
| Retry test sleeps for seconds | Ran real backoff delays | Inject clock/scheduler; assert delay as a value. |
| Fake sender passes every overload | Fake too simplistic, masking API bugs | Enforce exact overload contracts or fail fast on unsupported ones. |
| Test mistakes attachment for plain body | Looked up parts only by `text/plain` | Scope to main MIME body and check disposition. |

## 22. Test pyramid strategy for Spring Framework Mail

Avoiding a real SMTP server in **unit tests** does not mean skipping SMTP integration tests. A balanced test suite:


```text
            ┌─────────────────────────┐
            │ End-to-end mailbox test │
            │ few, controlled         │
            └───────────┬─────────────┘
               ┌────────┴────────┐
               │ SMTP integration│
               │ test server /   │
               │ provider sandbox│
               └────────┬────────┘
         ┌──────────────┴──────────────┐
         │ Unit tests (most numerous)  │
         │ renderer, service, MIME,    │
         │ validation, retry policy    │
         └─────────────────────────────┘
```

### 22.1. Unit tests

- No network and no secrets.
- Mock/fake `JavaMailSender`.
- In-memory `MimeMessage` with real Jakarta Mail.
- Test plain text/HTML, charsets, Unicode, attachments.
- Test validation branches, business rules, and retry decisions.

### 22.2. SMTP integration tests

- Connect to an SMTP sandbox or team-controlled test SMTP server.
- Verify TLS mode, AUTH where required, SMTP submission, and responses.
- Inspect SMTP envelope/headers and raw message received by the server.
- Never use real recipients or send real marketing emails.
- Include setup/teardown and separate from the unit-test suite.

### 22.3. End-to-end tests

- Run sparingly and with clear purpose.
- Use test mailboxes and authorized domains/recipients.
- Verify provider acceptance/delivery and mail-client rendering.
- Evaluate deliverability, spam/quarantine, or bounces when needed.
- Never block every code commit on an external provider's live uptime.

**A passing unit test shows logic passed verification, not that the entire SMTP system is healthy.**

## 23. Practice exercises

### Exercise 1 — Refactor service to constructor injection

A service currently instantiates `JavaMailSenderImpl` directly. Refactor it to depend on an injected `JavaMailSender`, then test sending a notification with Mockito without configuring SMTP.

### Exercise 2 — Capture SimpleMailMessage

Write a greeting mail service; test `To`, `From`, `Subject`, and plain text using `ArgumentCaptor<SimpleMailMessage>`.

### Exercise 3 — In-memory MimeMessage

Use `Session.getInstance(new Properties())` to create a `MimeMessage` and stub `createMimeMessage()`. Invoke the service and capture the message via `send(...)`.

### Exercise 4 — Plain and HTML alternatives

Create `MimeMessageHelper(message, true, "UTF-8")` and call `setText(plain, html)`. Traverse the MIME tree to verify both `text/plain` and `text/html` exist without calling SMTP.

### Exercise 5 — Unicode

Use name `Nguyễn Thị Ánh`, amount `450.000 ₫`, and emoji `🚀`. Serialize MIME to bytes, re-parse, and assert decoded content remains accurate.

### Exercise 6 — Attachment from ByteArrayResource

Attach `invoice.csv` from dummy bytes; assert filename, MIME type, and expected data. Do not read real files or fetch over the network.

### Exercise 7 — MimeMessagePreparator

The service calls `sender.send(preparator)`. Use `doAnswer` to run `prepare` on an in-memory `MimeMessage` and assert recipients/subject/body.

### Exercise 8 — Test simulated SMTP failures

Use Mockito `doThrow(new MailSendException("Simulated failure"))` and verify the service updates outcomes properly without disrupting any real SMTP server.

### Exercise 9 — Validation

When the recipient is unverified or unauthorized to receive an invoice, assert the appropriate exception and `verifyNoInteractions(sender)`.

### Exercise 10 — Sleep-free retry policy

Write `MailRetryPolicy` returning backoff delay and max attempts. Use `Clock.fixed` or fixed input timestamps to test outcomes without calling `Thread.sleep`.

### Exercise 11 — Outbox worker

Mock repository and sender; verify the worker calls `markAccepted` only after `send(...)` succeeds. On failure, verify retry/unknown state transitions without connecting to SMTP.

### Exercise 12 — Safe test profile

A `@SpringBootTest` sends real email during startup. Identify the listener/scheduler/test-connection causing side effects, replace the sender with a test double, and disable out-of-scope tasks.

### Exercise 13 — Test boundaries

Explain why `verify(sender).send(any(MimeMessage.class))` cannot prove:
- SPF/DKIM/DMARC pass;
- the SMTP relay accepted it;
- the email landed in Inbox;
- the user opened the email.

Propose matching integration/end-to-end tests.

### Exercise 14 — Fake vs mock

Compare a custom recording `InMemoryMailSender` against a Mockito mock. Point out pros, maintenance costs, and risks of spying on a real sender.

### Exercise 15 — Audit tests for zero network leaks

Define rules for the unit-test suite: no `JavaMailSenderImpl.send`, no secrets, no SMTP hostname dependency, and no mandatory local mail server. Describe how CI separates integration tests from unit tests.

## 24. Summary

**Avoiding real mail server dependencies in unit tests** is a foundational principle for fast, reliable, and safe testing of Spring Framework Mail:

1. Design services to depend on the **`MailSender` or `JavaMailSender` interface**, never instantiating a real SMTP sender inside business logic.
2. Use a **Mockito mock** at the sending boundary; for `SimpleMailMessage`, capture and assert fields directly.
3. For MIME, stub `createMimeMessage()` to return a **real in-memory `MimeMessage`**, then capture the object passed to `send(...)`.
4. Use `MimeMessageHelper` and real Jakarta Mail to inspect plain text, HTML, Unicode, charsets, the MIME tree, inline resources, and attachments **without opening an SMTP connection**.
5. For `MimeMessagePreparator`, run the callback explicitly via Mockito `Answer` when inspecting the built message.
6. Use mocked exceptions and pure policy tests to verify error branches, retries, idempotency, and outboxes without inducing SMTP provider outages.
7. Keep real `JavaMailSenderImpl`, spies, startup listeners, or unexpected schedulers out of unit tests.
8. Keep tests deterministic with non-sensitive fixtures, fixed clocks/locales, and no random MIME boundary comparisons.
9. Separate **SMTP integration** and **end-to-end deliverability** into dedicated test suites to verify what unit tests cannot prove.

As a result, any change in rendering or mail-sending logic is caught immediately in unit tests, unclouded by network, credential, or provider flakiness—and with zero risk of accidentally emailing real recipients during tests.
