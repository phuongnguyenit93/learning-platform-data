# Sending Messages via SMTP and Reading Received Messages in Spring Framework Mail

In Spring Framework Mail, a successful `JavaMailSender.send(...)` call indicates that the library completed the submission operation to the SMTP server according to the transport contract. However, if you only mock `JavaMailSender` and verify that the method was called, you still do not know whether an actual message was accepted by the SMTP server, whether the subject was encoded properly, whether HTML and plain text were packaged into proper MIME, or whether attachment bytes were lost.

**Send-then-read-back integration testing** closes that gap: the application sends via a real SMTP client to a test SMTP server, and then the test reads the message received by the server to verify content, headers, recipients, and MIME structure.

In the Java/Spring ecosystem, you can use GreenMail running in the same process as JUnit, or Mailpit/MailHog running in a container. This guide uses **GreenMail** for the primary examples because the server provides an API returning `MimeMessage[]`, aligning naturally with Jakarta Mail. In addition, it explains reading mailboxes via IMAP, testing a Spring Boot context, handling async flows, and what cannot be inferred from an SMTP capture test alone.

## 1. Testing Objectives

A send-and-read-back integration test should verify:

1. The SMTP client connected to a real test server, not a mock.
2. The server received the exact expected number of messages.
3. `From`, `To`, `Cc`, `Reply-To`, and required headers are set properly.
4. Subjects containing Vietnamese diacritics decode accurately.
5. Plain text or HTML contains the expected content.
6. The MIME structure contains all alternative parts, attachments, and inline resources if required by the use case.
7. Test resources are cleaned up; no messages from other tests skew results.
8. Asynchronous workflows use bounded signal waiting rather than fixed sleeps.

Diagram:

~~~text
JUnit 5
  |
  v
Application mail service
  |
  v
JavaMailSender (not mocked)
  |
  v
SMTP connection to localhost
  |
  v
GreenMail SMTP server
  |
  v
Captured MimeMessage[]
  |
  v
JUnit assertions on server-received message
~~~

When inspecting messages on the server side, you test the full transformation from application objects into transmitted wire data, rather than merely reading back your own input object.

## 2. Different Mail Testing Levels

| Level | Infrastructure Used | What It Verifies | What It Does Not Verify |
| --- | --- | --- | --- |
| Unit test with mock sender | Mock `JavaMailSender` | Sending call logic and arguments | Real SMTP transport and MIME |
| MIME construction test | `MimeMessageHelper`, Jakarta Mail | Headers, body, and MIME tree | Whether a server accepts the message |
| **SMTP integration test** | Real sender + test SMTP server | Server receives message and MIME can be read | Whether Internet providers deliver it |
| SMTP + IMAP test | Test mail server with mailboxes | Receiving via SMTP and retrieving via IMAP | Inbox placement outside test environment |
| Provider sandbox | Test account/SMTP provider | TLS, AUTH, quota/provider behavior | Whether every mailbox provider treats it identically |
| Production events | ESP/webhook/bounce/DSN | Operational feedback per data source | Whether a human definitely read the email |

GreenMail fits SMTP integration tests well; a unit test should not have to boot an entire Spring Boot context just to verify subject or body formatting logic.

## 3. Why Not Use Real Mailboxes in CI Tests?

A test sending to an external Internet account has many unstable factors:

- Internet connectivity, DNS, firewalls, and SMTP latency.
- Credentials, quotas, account status, MFA, and provider policies.
- Spam filters, quarantine, or mailbox rules.
- Inbox containing old emails or emails deleted by someone else.
- Test data potentially reaching unintended users.
- Provider outages breaking builds even when application code is unchanged.
- Parallel test runs competing for the same mailbox and quota.

A local SMTP server provides a repeatable environment, emits no outbound emails, and lets test code read messages immediately.

~~~text
Test environment:
  host      = 127.0.0.1
  port      = dynamic port of test server
  auth      = disabled or fake credentials
  recipient = user@example.test

Production environment:
  host      = configured SMTP provider
  auth      = securely managed credentials/tokens
  recipient = real recipient
~~~

Never commit production credentials in test source or enable SMTP debug logging that exposes passwords during pipeline runs.

## 4. GreenMail, Mailpit, and MailHog

### GreenMail

GreenMail is a mail server for Java tests. It supports SMTP along with mailbox retrieval protocols depending on configuration. For simple cases, you can start the server, send with `JavaMailSenderImpl`, and call `getReceivedMessages()`.

Advantages:

- Runs in the same JVM; Docker is not mandatory.
- Returns Jakarta Mail `MimeMessage` objects.
- Convenient for inspecting MIME parts, headers, and attachments.
- Fits JUnit 5 and Spring Boot integration tests.

### Mailpit / MailHog

Mailpit/MailHog are SMTP capture servers typically run as separate processes/containers with a web UI and API for inspecting messages. They are useful when multiple languages or microservices need a shared test endpoint, or when developers want to preview rendered HTML visually.

A test using Mailpit can look like:

~~~text
Spring JavaMailSender --> Mailpit SMTP:1025
                              |
                              v
                    Mailpit HTTP API/UI
                              |
                              v
                       Read captured mail
~~~

Ports and API endpoints depend on the tool/container in use. When implementing, follow the exact API schema for your version rather than assuming an HTTP response is a Jakarta Mail `MimeMessage`.

## 5. Dependencies for Spring Mail, JUnit, and GreenMail

Maven example; select a GreenMail version compatible with your project's Jakarta Mail stack:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.icegreen</groupId>
        <artifactId>greenmail</artifactId>
        <version>${greenmail.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`greenmail.version` is a project-defined property, not a built-in version. With Spring Boot 3/Spring Framework 6, code uses the `jakarta.mail.*` package and requires a Jakarta Mail-compatible GreenMail release. Spring Boot 2 projects often still use `javax.mail.*`; never mix incompatible namespaces and dependencies.

Gradle equivalent:

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-mail"
    testImplementation "org.springframework.boot:spring-boot-starter-test"
    testImplementation "com.icegreen:greenmail:<compatible-version>"
}
~~~

The last line is a version placeholder that must be replaced with an actual release per project. Code examples in this guide assume JUnit 5, Java 17+, and Jakarta Mail.

## 6. First Test: Sending Plain Text over SMTP and Reading It Back

This example uses an embedded SMTP server on a dynamic port. A real `JavaMailSenderImpl` sends over a TCP socket; the test then retrieves the `MimeMessage` from GreenMail.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;

import jakarta.mail.Message;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import java.util.Properties;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSenderImpl;

class PlainMailSmtpIntegrationTest {

    private GreenMail smtp;
    private JavaMailSenderImpl sender;

    @BeforeEach
    void setUp() {
        ServerSetup setup = new ServerSetup(
            0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP
        );

        smtp = new GreenMail(setup);
        smtp.start();

        sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(smtp.getSmtp().getPort());
        sender.setProtocol("smtp");
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "false");
        props.put("mail.smtp.starttls.enable", "false");
        props.put("mail.smtp.connectiontimeout", "3000");
        props.put("mail.smtp.timeout", "3000");
        props.put("mail.smtp.writetimeout", "3000");
    }

    @AfterEach
    void tearDown() {
        if (smtp != null) {
            smtp.stop();
        }
    }

    @Test
    void sendsAndReadsMessageFromSmtpServer() throws Exception {
        SimpleMailMessage outgoing = new SimpleMailMessage();
        outgoing.setFrom("sender@example.test");
        outgoing.setTo("recipient@example.test");
        outgoing.setSubject("Order confirmation");
        outgoing.setText("Order #A123 has been confirmed.");

        sender.send(outgoing);

        assertTrue(smtp.waitForIncomingEmail(5_000, 1));

        MimeMessage[] received = smtp.getReceivedMessages();
        assertEquals(1, received.length);

        MimeMessage actual = received[0];

        assertEquals(
            "sender@example.test",
            ((InternetAddress) actual.getFrom()[0]).getAddress()
        );

        assertEquals(
            "recipient@example.test",
            ((InternetAddress) actual.getRecipients(
                Message.RecipientType.TO)[0]).getAddress()
        );

        assertEquals("Order confirmation", actual.getSubject());
        assertTrue(actual.isMimeType("text/plain"));

        String text = (String) actual.getContent();
        assertTrue(text.contains(
            "Order #A123 has been confirmed."
        ));
    }
}
~~~

This code directly verifies **the message received by the SMTP server**, rather than simply reading back the initial `SimpleMailMessage`.

### Step-by-Step Explanation

1. `new ServerSetup(0, "127.0.0.1", ...)` requests an SMTP server on loopback with an OS-chosen port.
2. `smtp.start()` starts the server before the client connects.
3. `smtp.getSmtp().getPort()` retrieves the bound port.
4. `JavaMailSenderImpl` is configured to send to loopback, never a real provider.
5. `sender.send(outgoing)` transmits the message over SMTP.
6. `waitForIncomingEmail(...)` enforces a deadline, avoiding fixed sleeps.
7. `getReceivedMessages()` returns the MIME object captured by the server.
8. JUnit verifies message count, `From`, `To`, subject, and body.
9. `smtp.stop()` cleans up resources after the test.

If your mail server version does not support dynamic ports via that constructor, use GreenMail's fixed test port setup or an appropriate extension/container, while ensuring parallel tests avoid port collisions.

## 7. Why Read Back MimeMessage Instead of the Initial Object?

This assertion misses the point of an integration test:

~~~java
SimpleMailMessage outgoing = new SimpleMailMessage();
outgoing.setSubject("Hello");
sender.send(outgoing);

assertEquals("Hello", outgoing.getSubject());
~~~

It only confirms the object's subject was assigned beforehand. It does not prove the message reached the SMTP server.

Correct approach:

~~~java
MimeMessage actual = smtp.getReceivedMessages()[0];
assertEquals("Hello", actual.getSubject());
~~~

When verifying addresses:

~~~java
InternetAddress from =
    (InternetAddress) actual.getFrom()[0];

assertEquals(
    "sender@example.test",
    from.getAddress()
);
~~~

Use `InternetAddress.getAddress()` instead of `toString()` when you only want the email address, because `toString()` may include display names and quoting.

## 8. Waiting for Emails When Sending Asynchronously

With synchronous `JavaMailSender.send(...)`, the email is usually already received by the test SMTP server before the method returns. However, when sending via `@Async`, event listeners, workers, or queues, the caller may return before transmission occurs.

Avoid:

~~~java
Thread.sleep(2000);
assertEquals(1, smtp.getReceivedMessages().length);
~~~

Tests become both slow and flaky due to CI timing.

Better:

~~~java
assertTrue(smtp.waitForIncomingEmail(5_000, 1));
assertEquals(1, smtp.getReceivedMessages().length);
~~~

For multi-stage workflows, use Awaitility or bounded polling:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals(1, smtp.getReceivedMessages().length)
    );
~~~

The Awaitility example requires its corresponding test dependency. Awaitility is unnecessary when `waitForIncomingEmail` already satisfies the test condition. Always bound wait times so failures surface instead of hanging indefinitely.

## 9. Reading To, Cc, Reply-To, and Display Names

A message can have multiple recipients. Read them via Jakarta Mail:

~~~java
Address[] toAddresses = actual.getRecipients(
    Message.RecipientType.TO
);

Address[] ccAddresses = actual.getRecipients(
    Message.RecipientType.CC
);

Address[] replyToAddresses = actual.getReplyTo();
~~~

Example checking an address:

~~~java
InternetAddress to =
    (InternetAddress) toAddresses[0];

assertEquals("recipient@example.test", to.getAddress());
~~~

If the sender has a display name:

~~~java
helper.setFrom(new InternetAddress(
    "sender@example.test",
    "Example Store",
    "UTF-8"
));
~~~

You can verify that `getPersonal()` was decoded:

~~~java
InternetAddress from =
    (InternetAddress) actual.getFrom()[0];

assertEquals("Example Store", from.getPersonal());
~~~

For multiple recipients, compare as address sets if ordering is not a business requirement.

### Bcc Does Not Necessarily Appear in MIME Headers

Bcc is typically transmitted via the **SMTP envelope** and stripped from the message headers delivered to recipients. Therefore, calling `actual.getRecipients(Message.RecipientType.BCC)` will not always return Bcc recipients. To prove Bcc was accepted by the SMTP server, use the test server's envelope/recipient capture mechanism or inspect the target mailbox rather than relying solely on the Bcc header.

## 10. Testing Unicode and UTF-8 Charset

Vietnamese subjects, sender display names, and bodies are particularly prone to encoding errors.

Example:

~~~java
String expectedSubject =
    "Xác nhận thanh toán – Đơn hàng #123";

String expectedBody =
    "Xin chào, hóa đơn của bạn đã được phát hành.";
~~~

After sending and receiving:

~~~java
assertEquals(expectedSubject, actual.getSubject());

String content = (String) actual.getContent();
assertTrue(content.contains(expectedBody));
~~~

`MimeMessage.getSubject()` decodes MIME encoded-words. Never compare a raw `Subject` header directly against a Unicode string: the header may be encoded as `=?UTF-8?...?=` per RFC rules.

Also keep in mind:

- SMTP typically normalizes line endings to CRLF.
- Bodies may be transfer-encoded with quoted-printable or Base64.
- Charset is declared in `Content-Type`.
- Jakarta Mail `getContent()` helps decode text parts.
- For newlines, normalize only if differences fall outside the tested contract.

Tests should compare the **semantics of decoded content** rather than demanding identical raw message bytes on every run.

## 11. Creating an HTML Email with a Plain-Text Alternative

HTML emails often need a plain-text part for clients that do not render HTML.

~~~java
MimeMessage outgoing = sender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(outgoing, true, "UTF-8");

helper.setFrom("sender@example.test");
helper.setTo("recipient@example.test");
helper.setSubject("Electronic invoice");

helper.setText(
    "Your invoice has been generated.",
    "<html><body>"
        + "<h1>Invoice</h1>"
        + "<p>Your invoice has been generated.</p>"
        + "</body></html>"
);

sender.send(outgoing);

assertTrue(smtp.waitForIncomingEmail(5_000, 1));
MimeMessage actual = smtp.getReceivedMessages()[0];
~~~

Because multipart is used, `actual.getContent()` may return a `Multipart` rather than a `String`. Never write assertions assuming the top-level content is always `text/html`.

A MIME tree typically has layers:

~~~text
multipart/mixed or multipart/related
  |
  +--> multipart/alternative
  |       |
  |       +--> text/plain
  |       +--> text/html
  |
  +--> attachment or inline resource
~~~

Exact structure depends on helper mode and added parts. Tests should locate parts by content type rather than relying on hardcoded indices in a MIME tree.

## 12. Helper to Find text/plain and text/html

Example recursive MIME tree traversal method:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

static String findTextPart(
        Part part,
        String wantedMimeType) throws Exception {

    if (Part.ATTACHMENT.equalsIgnoreCase(
            part.getDisposition())) {
        return null;
    }

    if (part.isMimeType(wantedMimeType)) {
        Object content = part.getContent();
        if (content instanceof String text) {
            return text;
        }
    }

    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();

        for (int i = 0; i < multipart.getCount(); i++) {
            String text = findTextPart(
                multipart.getBodyPart(i),
                wantedMimeType
            );

            if (text != null) {
                return text;
            }
        }
    }

    return null;
}
~~~

Assertions:

~~~java
String plain = findTextPart(actual, "text/plain");
String html = findTextPart(actual, "text/html");

assertNotNull(plain);
assertNotNull(html);

assertTrue(plain.contains(
    "Your invoice has been generated."
));
assertTrue(html.contains("<h1>Invoice</h1>"));
~~~

This helper returns the first matching part and suffices for simple messages. For nested `message/rfc822`, multi-branch multipart alternatives, or forwarded emails, you may need a helper returning a list of parts with deeper structural checks.

Do not assert a specific multipart boundary string or assume MIME part ordering stays identical across all Jakarta Mail versions.

## 13. Sending Attachments and Verifying Received Bytes

Example attaching a small CSV:

~~~java
byte[] expectedBytes =
    "id,total\nA123,250000\n".getBytes(
        StandardCharsets.UTF_8
    );

MimeMessage outgoing = sender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(outgoing, true, "UTF-8");

helper.setFrom("sender@example.test");
helper.setTo("recipient@example.test");
helper.setSubject("Report");
helper.setText("Report file attached.", false);

helper.addAttachment(
    "report.csv",
    new ByteArrayResource(expectedBytes),
    "text/csv"
);

sender.send(outgoing);
assertTrue(smtp.waitForIncomingEmail(5_000, 1));

MimeMessage actual = smtp.getReceivedMessages()[0];
~~~

Helper to find a part by filename:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

static Part findAttachment(
        Part part,
        String expectedName) throws Exception {

    if (expectedName.equals(part.getFileName())) {
        return part;
    }

    if (part.isMimeType("multipart/*")) {
        Multipart mp = (Multipart) part.getContent();

        for (int i = 0; i < mp.getCount(); i++) {
            Part found = findAttachment(
                mp.getBodyPart(i),
                expectedName
            );
            if (found != null) {
                return found;
            }
        }
    }

    return null;
}
~~~

Verification:

~~~java
Part attachment = findAttachment(actual, "report.csv");

assertNotNull(attachment);
assertTrue(attachment.isMimeType("text/csv"));

try (InputStream stream = attachment.getInputStream()) {
    byte[] receivedBytes = stream.readAllBytes();
    assertArrayEquals(expectedBytes, receivedBytes);
}
~~~

Comparing bytes is better than coercing attachments to Strings for PDFs, PNGs, or binary files. For large attachments, verify digest and size instead of loading the entire payload into memory.

Import `org.springframework.core.io.ByteArrayResource`, `java.nio.charset.StandardCharsets`, and `java.io.InputStream` for the example above.

## 14. Inline Images with CID

An HTML email can use a Content-ID reference:

~~~java
MimeMessage outgoing = sender.createMimeMessage();

MimeMessageHelper helper =
    new MimeMessageHelper(outgoing, true, "UTF-8");

helper.setFrom("sender@example.test");
helper.setTo("recipient@example.test");
helper.setSubject("Store logo");

helper.setText(
    "<html><body>"
        + "<img src=\"cid:brandLogo\">"
        + "<p>Hello!</p>"
        + "</body></html>",
    true
);

helper.addInline(
    "brandLogo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

sender.send(outgoing);
~~~

Fixture `mail/logo.png` must exist in test resources. When building the message, set HTML text before adding inline resources per `MimeMessageHelper` guidance.

After reading back:

1. Find `text/html` containing `cid:brandLogo`.
2. Find the MIME part with the matching `Content-ID`.
3. Verify `Content-Type` is `image/png`.
4. Verify image bytes if required.
5. Do not hard-code multipart boundaries or part indices.

The `Content-ID` header may be wrapped in angle brackets like `<brandLogo>`, whereas HTML uses `cid:brandLogo`. Normalize this format when comparing IDs in tests.

## 15. Meaningful Headers in Integration Tests

You can inspect:

~~~java
String subject = actual.getSubject();
String messageId = actual.getMessageID();
String[] contentTypes = actual.getHeader("Content-Type");
String customId =
    actual.getHeader("X-Notification-ID", null);
~~~

If the application needs correlation, you can set a custom header before sending:

~~~java
outgoing.setHeader(
    "X-Notification-ID",
    notificationId.toString()
);
~~~

And verify on the receiving side:

~~~java
assertEquals(
    notificationId.toString(),
    actual.getHeader("X-Notification-ID", null)
);
~~~

Commonly useful headers:

| Header | Check |
| --- | --- |
| `From` | Sender identity |
| `To` / `Cc` | Displayed recipients |
| `Reply-To` | Reply address |
| `Subject` | Title and encoding |
| `Content-Type` | MIME type, charset, multipart |
| `Content-Disposition` | Inline/attachment |
| `Content-ID` | Inline content reference |
| `Message-ID` | Message correlation |
| `X-Notification-ID` | Application-defined ID |

Do not hard-code `Message-ID`, `Date`, or MIME boundaries in tests if they can be dynamically generated by libraries. Only assert fields that belong to your actual contract.

## 16. SMTP Capture Is Not IMAP or POP3

"Reading back received messages" can have two meanings:

**A. Reading directly from the SMTP capture server:**

~~~java
MimeMessage[] messages = smtp.getReceivedMessages();
~~~

This proves the test SMTP server captured the content. It does **not** execute an IMAP/POP3 session.

**B. Reading a mailbox via a retrieval protocol:**

~~~text
JavaMailSender --SMTP--> Test mail server
                              |
                              v
                        Mailbox storage
                              |
                       IMAP / POP3
                              |
                              v
                         Jakarta Mail Store
~~~

Approach B requires a server with IMAP/POP3 enabled and mailbox users. It is useful when the application itself reads inboxes, but unnecessary for SMTP sending tests.

## 17. Example: Sending via SMTP and Reading Back via IMAP

GreenMail can run SMTP and IMAP simultaneously:

~~~java
ServerSetup smtpSetup = new ServerSetup(
    0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP
);

ServerSetup imapSetup = new ServerSetup(
    0, "127.0.0.1", ServerSetup.PROTOCOL_IMAP
);

GreenMail server = new GreenMail(
    new ServerSetup[] { smtpSetup, imapSetup }
);

server.start();

try {
    server.setUser(
        "reader@example.test",
        "reader",
        "secret"
    );

    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("127.0.0.1");
    sender.setPort(server.getSmtp().getPort());

    SimpleMailMessage mail = new SimpleMailMessage();
    mail.setFrom("sender@example.test");
    mail.setTo("reader@example.test");
    mail.setSubject("SMTP + IMAP test");
    mail.setText("Content in mailbox.");

    sender.send(mail);
    assertTrue(server.waitForIncomingEmail(5_000, 1));

    Session session = Session.getInstance(new Properties());
    Store store = session.getStore("imap");

    try {
        store.connect(
            "127.0.0.1",
            server.getImap().getPort(),
            "reader",
            "secret"
        );

        Folder inbox = store.getFolder("INBOX");

        try {
            inbox.open(Folder.READ_ONLY);

            Message[] messages = inbox.getMessages();
            assertEquals(1, messages.length);

            assertEquals(
                "SMTP + IMAP test",
                messages[0].getSubject()
            );
        } finally {
            if (inbox.isOpen()) {
                inbox.close(false);
            }
        }
    } finally {
        store.close();
    }
} finally {
    server.stop();
}
~~~

This example uses Jakarta Mail classes `Session`, `Store`, `Folder`, `Message`, and classes imported in earlier examples. This reads the **test server's mailbox**, not an external Internet mailbox.

If the test server requires SMTP AUTH, configure separate credentials for the SMTP client; this local example focuses on receiving and reading via IMAP.

### How Does IMAP Differ from POP3?

- IMAP supports folders, flags, and mailbox synchronization.
- POP3 is primarily for downloading messages from a mailbox, with a limited folder model.
- SMTP is an email submission/relay protocol, not an inbox-reading protocol.

`JavaMailSender` is not designed to read mail. Retrieval uses Jakarta Mail `Store`/`Folder` over IMAP or POP3.

## 18. Testing a Spring Boot Context with @SpringBootTest

Previous examples created the sender manually. To test Spring Boot auto-configuration, dependency injection, and real services, use `@SpringBootTest`.

Crucially, the SMTP server must be running **before the Spring context resolves host/port**.

~~~java
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class SpringBootMailIntegrationTest {

    private static final GreenMail SMTP = new GreenMail(
        new ServerSetup(
            0, "127.0.0.1", ServerSetup.PROTOCOL_SMTP
        )
    );

    static {
        SMTP.start();
    }

    @DynamicPropertySource
    static void overrideMailProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
            "spring.mail.host",
            () -> "127.0.0.1"
        );
        registry.add(
            "spring.mail.port",
            () -> SMTP.getSmtp().getPort()
        );
        registry.add(
            "spring.mail.properties.mail.smtp.auth",
            () -> "false"
        );
        registry.add(
            "spring.mail.properties.mail.smtp.starttls.enable",
            () -> "false"
        );
    }

    @Autowired
    private OrderMailService orderMailService;

    @AfterAll
    static void stopMailServer() {
        SMTP.stop();
    }

    @Test
    void applicationServiceSubmitsMail() throws Exception {
        orderMailService.sendConfirmation(
            "buyer@example.test",
            "ORDER-123"
        );

        assertTrue(SMTP.waitForIncomingEmail(5_000, 1));

        MimeMessage[] messages = SMTP.getReceivedMessages();
        assertEquals(1, messages.length);

        assertEquals(
            "Order confirmation ORDER-123",
            messages[0].getSubject()
        );
    }
}
~~~

`OrderMailService` is an application service assumed to have a `sendConfirmation` method and matching bean. Add Spring Test imports `@SpringBootTest`, `@DynamicPropertySource`, `DynamicPropertyRegistry`, `@DirtiesContext`, JUnit `@AfterAll`, `@Test`, `@Autowired`, and GreenMail to test sources.

Static initialization guarantees GreenMail starts before Spring Boot resolves dynamic properties. `@DirtiesContext` prevents reusing a Spring context pointing to a server stopped after the class finishes. For large suites, manage lifecycles via test extensions or containers to reduce the risk of static servers leaking if context bootstrap fails.

### @SpringBootTest Is Not Needed for Every Test

When testing transport and MIME alone, JUnit + GreenMail + `JavaMailSenderImpl` can be faster and simpler. Only boot the full context when verifying Spring wiring, property binding, business services, or workflows.

## 19. Test Profile and Preventing Production SMTP Usage

You can use a test profile:

~~~yaml
# application-test.yml
spring:
  mail:
    host: 127.0.0.1
    username:
    password:
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
~~~

The port is dynamically overridden from GreenMail or a container. With `@ActiveProfiles("test")`, ensure the test actually loads the expected profile and that production environment variables do not override host or credentials.

Safety measures:

- Never load production SMTP secrets into CI tests.
- Only use test recipient domains.
- Block production endpoints in test environments when needed.
- Never print MIME bodies/credentials indiscriminately to test logs.
- Never send real emails just to make an integration test pass.
- Consider verifying runtime host/port before running tests if the project pulls from multiple config sources.

## 20. Negative SMTP Test Cases

An SMTP integration test should not cover only the happy path. You can build scenarios for:

| Scenario | Symptom | Expected Assertion |
| --- | --- | --- |
| SMTP server not started | Connection refused | Sender throws send error, no message captured |
| Wrong host/port | Connection timeout/refused | Clear transport error |
| Invalid SMTP AUTH | Server rejects AUTH | Message not submitted |
| Recipient rejected | `RCPT TO` rejection | Error classified by recipient/transport |
| Message too large | `DATA`/policy rejection | Not marked `SUBMITTED` |
| MIME preparation error | Invalid address/attachment source | Failure detected |
| Duplicate business event | Two application calls | Only one logical notification if idempotency exists |
| Sending via `@Async` | Caller returns before worker | Test waits for server capture with a deadline |
| Outbox retry after temporary SMTP error | First attempt fails | Message arrives only when retry window triggers |
| Bcc | Bcc header may be stripped | Verify exact envelope/mailbox |
| Wrong charset | Vietnamese diacritics corrupted | Subject/body assertion fails |
| Wrong attachment | Mismatched bytes/filename | MIME assertion fails |

Not every SMTP test server supports fault injection at every phase. To simulate losing the response at the end of `DATA`, you may need a protocol-controlling SMTP stub/proxy or a server supporting custom responses.

## 21. Using @Async or @TransactionalEventListener

An application may publish an event after commit and send email via a listener:

~~~java
@Component
public class OrderMailListener {

    private final OrderMailService mailService;

    public OrderMailListener(OrderMailService mailService) {
        this.mailService = mailService;
    }

    @Async("mailTaskExecutor")
    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onConfirmed(OrderConfirmedEvent event) {
        mailService.sendConfirmation(
            event.recipient(),
            event.orderCode()
        );
    }
}
~~~

Tests must trigger a **genuinely committed transaction** for an `AFTER_COMMIT` listener to run. A test method annotated with `@Transactional` rolls back by default at the end and will not trigger after-commit events like production.

Therefore:

- Do not annotate the entire test with `@Transactional` by default when testing `AFTER_COMMIT`.
- Invoke the real use case through the Spring proxy so transactions open/commit as in production.
- Wait for messages with a deadline.
- Do not confuse a task accepted by the executor with an SMTP message reaching the server.
- If using an outbox, verify business data and the outbox row commit together before the worker sends.
- Avoid fixed sleeps when waiting for listeners.

With a retrying outbox worker, a test can inspect both durable job state and GreenMail-received messages, though it should not depend on overly long production scheduler intervals; configure test-specific timing so tests finish quickly.

## 22. Asserting Message Counts and Avoiding State Leakage

If a test assumes only one message exists:

~~~java
assertEquals(1, smtp.getReceivedMessages().length);
~~~

it is only meaningful when the mailbox/capture server is clean or when filtering by the test's correlation ID.

Sources of state leakage:

- A previous test sent emails into the same GreenMail instance.
- Parallel tests share the same server.
- Schedulers/background workers are still running.
- Another listener sends unintended notifications.
- Outbox contains leftover records from the test database.
- Tests share the same recipient and the same subject.

Choose an isolation strategy:

1. Start/stop GreenMail per test.
2. Use a dedicated server per test class.
3. Purge the mailbox/captured messages using the appropriate API when reusing a server.
4. Attach a custom `X-Notification-ID` to filter messages belonging to the test.
5. Use a clean test database or isolated fixtures.
6. Ensure async tasks have completed before teardown.

Do not rely on JUnit test execution order or assume `getReceivedMessages()[0]` is always the right message when multiple messages occur.

## 23. Correlation IDs to Locate the Right Message

When testing complex workflows, add a stable ID:

~~~java
mime.setHeader(
    "X-Notification-ID",
    notificationId.toString()
);
~~~

Tests can filter messages by this header instead of ordering:

~~~java
MimeMessage matched = null;

for (MimeMessage candidate : smtp.getReceivedMessages()) {
    String id = candidate.getHeader(
        "X-Notification-ID",
        null
    );

    if (notificationId.toString().equals(id)) {
        matched = candidate;
        break;
    }
}

assertNotNull(matched);
~~~

Not every production provider preserves custom headers, yet in SMTP capture tests it is helpful when configuration and the test server allow it.

`Message-ID` is an email-specific identifier; do not assume it is a provider queue ID or guarantees SMTP deduplication. For business idempotency, use a dedicated notification/event ID.

## 24. SMTP Acceptance Differs from Actual Delivery

A test receiving a message via GreenMail proves **the test SMTP server accepted and stored the message**. It does not prove:

- The final recipient on the Internet received the email.
- The email landed in Inbox rather than Spam.
- Internet providers rated DKIM/SPF/DMARC as passing.
- Attachments were not blocked by downstream filters.
- The recipient opened or read the message.
- The production SMTP provider permits the current sender/account.

To verify those aspects, use a provider sandbox, deliverability monitoring, bounce/delivery events, or a controlled real-world testing process.

Do not write test assertions or report "delivered" solely from `JavaMailSender.send()` or GreenMail capture. Proper statuses are usually `SUBMITTED_TO_TEST_SMTP` or `CAPTURED_BY_TEST_SERVER`.

## 25. Testing TLS and SMTP AUTH

Local plaintext tests often disable AUTH/STARTTLS to focus on message contents. However, production may require port 587 STARTTLS, port 465 implicit TLS, or OAuth2/XOAUTH2.

You can create dedicated tests for:

- Server requires AUTH and client has test username/password.
- Invalid credentials must produce an authentication error.
- `STARTTLS` required prevents sending if the server lacks TLS.
- Certificate hostname/trust validation in the test environment.
- Explicit SMTP connection/read/write timeouts.
- Client selects the proper AUTH mechanism when required by the provider.

Never use trust-all TLS bypasses in production just to pass tests. If tests need self-signed certificates, use a separately managed test truststore.

Do not expect default GreenMail to simulate every OAuth2, quota, throttling, or TLS policy of a real provider. Those require dedicated sandbox/contract tests.

## 26. Using a Mailpit Container Instead of GreenMail

If your team already uses Docker/Testcontainers, you can run a Mailpit SMTP capture container with appropriate SMTP and HTTP API ports.

Flow:

~~~text
@Testcontainers / Docker
          |
          v
Mailpit container
     |       |
     |       +--> HTTP API / Web UI
     |
     +--> SMTP endpoint
             ^
             |
      JavaMailSender
~~~

Steps:

1. Start the container before the Spring Boot context.
2. Read the container's host and mapped SMTP port.
3. Override `spring.mail.host` and `spring.mail.port`.
4. Invoke the real application service to send.
5. Wait for the captured message to appear via the HTTP API.
6. Read JSON/raw MIME and assert subject, recipients, and body.
7. Stop the container and clean up test data.

HTTP endpoints, JSON formats, and raw MIME retrieval must match the Mailpit version in use; do not hard-code unverified endpoints. When tests only need Java `MimeMessage` directly, GreenMail often involves fewer steps.

## 27. Common Test Design Mistakes

| Anti-Pattern | Issue | Better Approach |
| --- | --- | --- |
| Mocking `JavaMailSender` and calling it an SMTP integration test | Does not verify real transport | Use a test SMTP server |
| Asserting on the `SimpleMailMessage` object before sending | Does not prove server received it | Read `MimeMessage` from server |
| Sending to Gmail/real accounts in CI | Flaky, leaks, quota and cost | Local SMTP capture |
| Hard-coding an SMTP port for all tests | Collisions in parallel tests | Dynamic ports |
| Not stopping the test server | Thread/socket leaks | Explicit lifecycle/teardown |
| Fixed 5-second sleep | Slow and flaky tests | Bounded wait/poll |
| Reading index 0 when mailbox has other messages | Wrong assertions | Clear state/correlation IDs |
| Casting top-level multipart to `String` | `ClassCastException` | Traverse MIME tree |
| Checking only attachment filename | Misses corrupted/wrong file | Compare bytes/digest |
| Comparing raw encoded `Subject` | Flexible charset encoding | Use `getSubject()` |
| Comparing raw MIME boundaries | Dynamic boundaries | Assert semantics/parts |
| Reading `Bcc` from headers and expecting it | `Bcc` may be stripped from headers | Verify envelope/mailbox |
| Equating captured with delivered | Overstating guarantees | Distinguish submission/delivery |
| `@Transactional` test rolls back yet expects `AFTER_COMMIT` | Listener never runs | Commit genuinely in test workflow |
| Using SMTP debug logs containing credentials | Sensitive data leak | Disable/sanitize debug |
| Not isolating async schedulers | Unexpected messages | Scope tests and lifecycles |
| Mixing `javax.mail` with `jakarta.mail` | Type/dependency errors | Choose compatible versions |

## 28. Implementation Workflow in a Spring Project

A practical roadmap:

1. **Identify the mail service** to test, such as order confirmation sending.
2. **Route sending through a clear interface/adapter**; unit tests can mock it, while integration tests use the real sender.
3. **Add the GreenMail test dependency** compatible with Jakarta Mail.
4. **Start a local SMTP server** on loopback, preferring a dynamic port.
5. **Configure `JavaMailSender`** to point to test host/port; never use production credentials.
6. **Invoke the use case** rather than manually building messages if verifying full wiring.
7. **Wait for the message to reach the server** with a finite timeout.
8. **Read the received `MimeMessage`**, asserting `From`/`To`/`Subject`/`Text`.
9. **For HTML/multipart**, traverse the MIME tree and verify plain text/HTML.
10. **For attachments/inline**, verify filename, MIME type, `Content-ID`, and bytes.
11. **For async/events**, ensure transaction commit and worker execution.
12. **Isolate test state**, cleaning up servers and background tasks.
13. **Add negative cases**: AUTH failures, recipient rejections, timeouts, duplicates.
14. **Use a provider sandbox** when testing real provider configurations, instead of expecting GreenMail to simulate every quirk.

## 29. Key Takeaways

- Email sending integration tests need **a real `JavaMailSender` + a test SMTP server**, not mocks alone.
- GreenMail lets you call `getReceivedMessages()` to retrieve `MimeMessage[]` accepted by the server.
- Sending via SMTP and reading from a capture server differs from reading an Inbox via IMAP/POP3.
- Use dynamic ports and loopback to avoid conflicts and accidental production targeting.
- Use bounded timeouts/polling instead of fixed `Thread.sleep` calls.
- Inspect the message **on the server side**, not just the input object.
- `getSubject()` and `getContent()` help verify decoded text.
- Multipart HTML/alternative/attachments require traversing the MIME tree.
- For attachments, compare bytes or digests to catch corrupted/truncated files.
- For inline content, check `cid:...` and the `Content-ID` part.
- `Bcc` does not always appear in headers of the received message.
- In `@SpringBootTest`, the SMTP server must start before the context resolves dynamic ports.
- A `@Transactional` test that rolls back by default may never fire `AFTER_COMMIT` listeners.
- Tests with async/outbox flows must await messages by correlation ID and isolate background tasks.
- GreenMail capture proves the test SMTP server received the message; **it does not prove a real email reached an Inbox**.
- Tests must stop the server and never use production credentials or real recipients.

**Core takeaway:** send an email through a real SMTP client to a test server, and then read **the exact MIME message accepted by the server**. Verify what matters to users and the application - recipients, subject, content, MIME structure, attachments, and encoding - instead of merely checking that a method was called. That boundary keeps Spring Framework Mail integration tests genuinely valuable while remaining fast, safe, and repeatable.
