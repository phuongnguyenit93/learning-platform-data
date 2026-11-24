# Fake Mail Server or SMTP Test Container

## 1. Why Do We Need a Fake Mail Server for Integration Testing?

In **Spring Framework Mail**, developers often call `JavaMailSender.send(...)` to submit an email to an SMTP server. A unit test can mock `JavaMailSender` and verify the method was called, but that **does not prove the application builds a valid MIME message, connects to the right SMTP host/port, or transmits the content to an SMTP server**.

Integration testing bridges this gap by having the application communicate with a **test mail server** over the real SMTP protocol, while **not delivering emails out to the Internet to real recipients**.

~~~text
                  Application Under Test
                            |
                            | Spring Mail / JavaMailSender
                            | SMTP protocol
                            v
                Fake SMTP server / container
                            |
                   +--------+---------+
                   |                  |
                   v                  v
              Captured MIME     Test API / UI / IMAP
                   |                  |
                   +--------+---------+
                            v
                    Test assertions
            recipient, subject, body, headers,
                   HTML, text, attachment
~~~

A fake SMTP server can help detect:

- `spring.mail.host` or `spring.mail.port` pointing to the wrong environment.
- The SMTP client failing to connect or timing out.
- Sender/recipient addresses, headers, and subject being set incorrectly.
- Vietnamese-language emails suffering from charset or encoding errors.
- Incorrect MIME structure for HTML/plain text.
- Missing attachments, wrong filenames, or wrong content types.
- `@Async`/worker/outbox not actually sending emails.
- A business event accidentally generating multiple duplicate emails.

A clear boundary to keep in mind: **a test SMTP server confirms the application sends to that server; it does not prove real inbox deliverability**. This test does not replace checking DNS/SPF/DKIM/DMARC, bounces, spam filtering, reputation, or production provider quotas.

## 2. Testing Tiers in an Email-Sending Application

You should not use an SMTP container for every test. Different testing levels serve different goals:

| Test Level | Replacement / Real Components | What It Verifies | What It Does Not Verify |
| --- | --- | --- | --- |
| Unit test with mocked `JavaMailSender` | Does not open SMTP | Business flow, passed-in data, call counts | SMTP connection, real MIME serialization |
| Unit test building `MimeMessage` | Real Jakarta Mail object; mock/fake sender | Headers, MIME tree, text/HTML/attachment | SMTP handshake and network transmission |
| Integration test with fake SMTP | Real Spring Mail + SMTP protocol; server retains messages | Connection, acceptance, captured content | Internet email delivery |
| Integration test with SMTP container | Test server running in Docker/Testcontainers | Repeatability, network boundary, runtime configuration | Specific policies of a real provider |
| Staging with an authorized provider | Real mail provider and test addresses | Credentials, TLS, domain, quota/API within staging scope | Not fully representative of every mailbox/inbox |

**Recommendation:** Use mocks to test pure business branches and use a set of integration tests with fake SMTP to verify the full path from `JavaMailSender` to the message retained on the fake server.

### 2.1. How Does a Mock Differ from Fake SMTP?

Unit test example:

~~~java
@Test
void requestsMailSend() {
    JavaMailSender sender = mock(JavaMailSender.class);
    NotificationService service = new NotificationService(sender);

    service.notifyOrderConfirmed("order-123");

    verify(sender).send(any(SimpleMailMessage.class));
}
~~~

If `NotificationService` only creates a `SimpleMailMessage`, this test checks **interaction calls**. It does not perform an SMTP handshake or send bytes to a server.

In an integration test, the real `JavaMailSender` bean is configured by Spring Boot. The fake server receives the message and lets the test retrieve the data for assertions. Both test types complement each other; there is no need to choose one and discard the other.

## 3. Test Mail Server Options

Commonly used tools:

| Tool | Model | How Messages Are Observed | Best Suited When |
| --- | --- | --- | --- |
| **Mailpit** | SMTP sink, typically run as a container/standalone process | Web UI and HTTP API | Local email testing, integration tests, visual MIME inspection |
| **MailHog** | SMTP sink for development environments | Web UI and HTTP API | Projects already using MailHog, quick SMTP checks |
| **GreenMail** | Java-based fake mail server, runnable in-process or as a container | Java API, IMAP/POP3/SMTP depending on configuration | Java/Jakarta Mail integration tests, direct message content assertions |
| **Wiser / SubEthaSMTP** | Lightweight SMTP server inside the test process | Java API receiving messages | Lightweight SMTP sending tests without needing a web UI |
| **Custom SMTP test container** | Container running an SMTP service for testing | Per server API/logs/protocol | Need to simulate custom policies or handshakes |

The choice depends on testing requirements, Docker availability in CI, and whether messages need to be read via API, IMAP, or simply accepted over SMTP.

### 3.1. Mailpit and MailHog Are SMTP Sinks

An SMTP sink is a mail server that **receives and retains emails in a test environment** instead of forwarding them to the Internet. This lets developers view messages in a UI while automated tests can call an API to verify them.

Do not assume all SMTP sinks support the same API. For example, Mailpit and MailHog APIs are not identical; test code must follow the documentation of the specific tool and version in use.

### 3.2. GreenMail When Java Interaction Is Needed

GreenMail is often a good fit when you want to:

- Start an SMTP server inside the test process.
- Retrieve the list of received `MimeMessage` instances via a Java API.
- Inspect multipart sections, attachments, and headers.
- Also use IMAP/POP3 in tests that require receiving mail.

Be sure to choose a **GreenMail version compatible with your application's Jakarta Mail or JavaMail API**. For Spring Boot 3 and above, imports use `jakarta.mail.*`; an older dependency using only `javax.mail.*` can cause type conflicts.

### 3.3. When to Use a Container?

Containers are useful if you want:

- A mail server running independently from the test JVM.
- The same image/server on developer machines and in CI.
- No in-process server affecting other classloaders/tests.
- To test `spring.mail.*` settings over a real network host/port.
- Reproducible infrastructure via Docker Compose or Testcontainers.

A container does not automatically make tests "more realistic" in every aspect. If you only need to verify that `MimeMessage` is constructed properly without network involvement, in-process GreenMail/Wiser can be lighter.

## 4. Running Mailpit Locally with Docker Compose

A convenient approach is running Mailpit on your development machine:

~~~yaml
# compose.yaml
services:
  mailpit:
    image: axllent/mailpit:v1.27.5
    ports:
      - "127.0.0.1:1025:1025"   # SMTP from host
      - "127.0.0.1:8025:8025"   # Web UI / API from host
~~~

The tag `v1.27.5` is a **pinned illustrative version**; your project should choose a verified tag and proactively update it according to its dependency policy. In CI, avoid using `latest` if builds must be highly reproducible.

Run the local environment:

~~~bash
docker compose up -d mailpit
~~~

With this mapping:

- `localhost:1025` on the host machine: Mailpit's SMTP.
- `http://localhost:8025` on the host machine: web interface for viewing emails and API.
- Ports are bound to `127.0.0.1` to restrict access from external networks.

If the Spring application also runs **inside Docker Compose**, do not use `localhost` inside the application container to point to the Mailpit container. Inside a Compose network, use the service hostname:

~~~yaml
spring:
  mail:
    host: mailpit
    port: 1025
~~~

When the application runs directly on the host machine, use `127.0.0.1` or `localhost`.

### 4.1. Spring Boot Configuration for Local Use

Create a local/test profile configuration without production credentials:

~~~yaml
# application-local.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

This example is **exclusively for an SMTP sink running locally or on an isolated test network**. Never copy `auth=false` and disabled TLS to production SMTP on a public network. With a real provider, configure AUTH/TLS according to security policies.

In Spring Boot, `spring.mail.properties` is a map of Jakarta Mail properties. Square brackets in YAML keys preserve dotted segments such as `mail.smtp.timeout` during map binding.

### 4.2. Sending a Test Email

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class DemoMailService {

    private final JavaMailSender mailSender;

    public DemoMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendDemo() {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.test");
        message.setTo("student@example.test");
        message.setSubject("Test sending email via fake SMTP");
        message.setText("Test email content sent to Mailpit.");
        mailSender.send(message);
    }
}
~~~

After calling the method, open the Mailpit Web UI at `http://localhost:8025` to view the retained message. There is no reason to send a real email out to the Internet to verify this step.

### 4.3. What the UI Helps Developers Observe

Depending on the server version, the UI/API can help inspect:

- The `To`, `Cc`, `Bcc`, and `From` addresses of the message.
- Subject, plain text content, rendered HTML, and HTML source.
- MIME structure, attachments, and content types.
- Headers such as Message-ID, Reply-To, and Date.
- The timestamp when the fake server received the email.

Do not confuse "Mailpit received the email" with "the target mailbox on the Internet received it". Mailpit is acting as the final sink for the test.

## 5. Integrating an SMTP Test Container into JUnit with Testcontainers

For automated integration tests, **Testcontainers** can spin up Mailpit per test lifecycle. Tests do not depend on a developer having run `docker compose up` beforehand.

Typically required components:

~~~text
Spring Boot application
    ├── spring-boot-starter-mail
    └── spring-boot-starter-test

Integration test
    ├── Testcontainers JUnit 5 integration
    ├── Testcontainers core
    └── Docker-compatible container runtime
~~~

Manage dependency versions using the Spring Boot/Testcontainers BOM suited to your project. Do not mix arbitrary versions across Spring Boot, Jakarta Mail, and test libraries.

### 5.1. Testcontainers Dynamic Port Mapping

In Testcontainers, the port **inside the container** is usually fixed (`1025` for SMTP), while the port exposed on the host machine is **randomized** to avoid conflicts across multiple test suites:

~~~text
Test JVM                           Mailpit container

localhost:randomHostPort  ------->  1025/tcp SMTP
localhost:randomApiPort   ------->  8025/tcp HTTP API
~~~

Therefore, tests must not hard-code host port `1025`. Use `container.getHost()` and `container.getMappedPort(1025)`. This approach works reliably with both local Docker and remote container runtimes supported by Testcontainers.

### 5.2. Configuring the JavaMailSender Bean with @DynamicPropertySource

An example Spring Boot integration test using JUnit 5 and Testcontainers:

~~~java
package com.example.mail;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class MailpitSmtpIntegrationTest {

    private static final int SMTP_PORT = 1025;
    private static final int API_PORT = 8025;

    @Container
    static final GenericContainer<?> mailpit =
            new GenericContainer<>(
                    DockerImageName.parse("axllent/mailpit:v1.27.5"))
                    .withExposedPorts(SMTP_PORT, API_PORT)
                    .waitingFor(
                            Wait.forHttp("/api/v1/messages")
                                    .forPort(API_PORT)
                                    .forStatusCode(200));

    @DynamicPropertySource
    static void configureMail(DynamicPropertyRegistry registry) {
        registry.add("spring.mail.host", mailpit::getHost);
        registry.add("spring.mail.port",
                () -> mailpit.getMappedPort(SMTP_PORT));
        registry.add("spring.mail.properties.mail.smtp.auth",
                () -> false);
        registry.add("spring.mail.properties.mail.smtp.starttls.enable",
                () -> false);
        registry.add("spring.mail.properties.mail.smtp.connectiontimeout",
                () -> 5000);
        registry.add("spring.mail.properties.mail.smtp.timeout",
                () -> 5000);
    }

    @Autowired
    JavaMailSender mailSender;

    @Test
    void canSubmitMailToSmtpTestContainer() {
        String subject = "SMTP test " + UUID.randomUUID();

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("notifications@example.test");
        message.setTo("student@example.test");
        message.setSubject(subject);
        message.setText("Hello from Spring Mail!");

        mailSender.send(message);

        // Next step: fetch the captured email from Mailpit's HTTP API
        // and verify subject/recipient/body.
    }
}
~~~

The example test above verifies that the send call does not throw an exception when the SMTP sink is running; to truly verify that **the right email was received**, add assertions against the Mailpit API as shown in the next section. Unused imports/assertions in the snippet can be removed when copying into a project.

**Technical note:** `@DynamicPropertySource` supplies host/port **before** Spring creates `JavaMailSender`. `@Container` and `@Testcontainers` manage the container lifecycle when tests start and stop.

If a previous Spring context already cached a `JavaMailSender` with different properties, organize your test classes and context caching appropriately; do not mutate a singleton bean after context creation to "swap ports" arbitrarily.

## 6. Reading Received Emails via the Mailpit HTTP API

A good integration test should verify that **the SMTP server actually retained the expected message**, rather than merely checking that `send(...)` did not throw an exception.

Mailpit provides an HTTP API to retrieve captured emails. In versions supporting the `GET /api/v1/messages` endpoint, the JSON response contains a list of messages, typically including ID, subject, and sender/recipient metadata. Pin your image and test adapter to the **API version in use**; do not assume the MailHog API is compatible with Mailpit.

A simple Java helper:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class MailpitApiClient {

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();
    private final URI messagesUri;

    public MailpitApiClient(String host, int apiPort) {
        this.messagesUri = URI.create(
                "http://" + host + ":" + apiPort + "/api/v1/messages");
    }

    public JsonNode listMessages() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(messagesUri)
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                    "Mailpit API returned " + response.statusCode());
        }

        return mapper.readTree(response.body());
    }
}
~~~

This helper only retrieves the message list. Specific JSON fields and endpoints for reading full MIME/headers must be checked against the API documentation of your **pinned Mailpit version**.

### 6.1. Asserting by Unique Subject

To avoid interference between tests sharing the same container, generate a unique subject for each test and look up that specific message:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.stream.StreamSupport;

@Test
void smtpContainerCapturesTheMessage() {
    String subject = "SMTP Test " + UUID.randomUUID();

    SimpleMailMessage email = new SimpleMailMessage();
    email.setFrom("notifications@example.test");
    email.setTo("student@example.test");
    email.setSubject(subject);
    email.setText("Test content sent via Spring Mail");

    mailSender.send(email);

    MailpitApiClient api = new MailpitApiClient(
            mailpit.getHost(),
            mailpit.getMappedPort(API_PORT));

    await()
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(200))
            .untilAsserted(() -> {
                var response = api.listMessages();
                boolean found = StreamSupport.stream(
                        response.path("messages").spliterator(), false)
                        .anyMatch(item ->
                                subject.equals(
                                        item.path("Subject").asText()));
                assertThat(found).isTrue();
            });
}
~~~

This example belongs inside the `MailpitSmtpIntegrationTest` class from the previous section, using the declared `mailSender`, `mailpit`, and `API_PORT` fields. `Awaitility` is usually included in Spring Boot's test dependencies; if your project lacks it, add the corresponding test dependency.

Advantages of this approach:

- No fixed `Thread.sleep(2000)`.
- Allows a small delay for the message to appear in the API.
- Distinguishes emails across test cases using a randomized subject.
- Fails clearly on timeout instead of hanging indefinitely.

If the fake server returns a stable message ID, you can further query detailed contents and assert recipients, plain text, HTML, or attachments. Do not assert the entire JSON response as an immutable string because timestamps, IDs, and metadata change across runs.

### 6.2. Centralizing the Test API Adapter

Do not copy Mailpit JSON-parsing code into dozens of test files. Create a test support class such as `MailpitApiClient` with operations like:

~~~text
listMessages()
findByUniqueSubject(subject)
readMessage(id)
readRawMessage(id)
clearMailboxForIsolatedTest()
~~~

These methods represent a **suggested helper design**, not built-in Mailpit signatures. The implementation must call endpoints supported by the chosen Mailpit version's documentation.

Centralizing the adapter makes changing Mailpit API versions or switching tools easier without editing every test case.

## 7. Testing MIME Messages: HTML, Plain Text, and Charset

A transactional email typically contains both HTML and plain text:

~~~text
MimeMessage
  |
  +-- multipart/alternative
        |
        +-- text/plain; charset=UTF-8
        |
        +-- text/html; charset=UTF-8
~~~

When attachments are added, the MIME tree may nest `multipart/mixed` or `multipart/related`, depending on how `MimeMessageHelper` configures multipart mode. Do not hard-assert that every email has **one single fixed MIME tree structure**, because the implementation and the presence of inline resources/attachments can legitimately alter nesting.

### 7.1. Creating HTML/Plain Text Emails with MimeMessageHelper

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendWelcomeMail(String recipient)
        throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message, true, "UTF-8");

    helper.setFrom("notifications@example.test");
    helper.setTo(recipient);
    helper.setReplyTo("support@example.test");
    helper.setSubject("Chào mừng đến với hệ thống");

    String plain = "Xin chào Lan! Tài khoản của bạn đã được tạo.";
    String html = """
            <html>
              <body>
                <h1>Xin chào Lan!</h1>
                <p>Tài khoản của bạn đã được tạo.</p>
              </body>
            </html>
            """;

    helper.setText(plain, html);
    mailSender.send(message);
}
~~~

This snippet uses a Java text block; if the project uses an older Java version, use regular strings or a template engine. The test objective is to verify the MIME message contains both content variants and that Vietnamese characters are preserved properly over SMTP.

### 7.2. Valuable Assertions

With a tool that lets you inspect `MimeMessage` or raw MIME, you can check:

- `From` header matches the application sender.
- `To`, `Cc`, `Bcc` lists match the generated delivery.
- `Reply-To` if required by the product.
- Subject decodes Unicode properly.
- A `text/plain` part is present.
- A `text/html` part is present.
- Vietnamese content and characters such as `&`, `<`, `>` are not corrupted by encoding.
- Template variables are mapped to their expected values.
- Headers or attachments do not unexpectedly expose sensitive tokens.

Do not compare raw messages byte-for-byte without a clear reason: MIME boundaries, Message-ID, header folding, and Date can vary across sends.

### 7.3. Helper to Extract Content by MIME Type

With Jakarta Mail, a test helper can traverse the MIME tree:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;

public final class MimeTestSupport {

    public static String findTextPart(Part part, String mimeType)
            throws Exception {

        if (part.isMimeType(mimeType)) {
            Object content = part.getContent();
            return content instanceof String text ? text : null;
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                String found = findTextPart(child, mimeType);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }
}
~~~

This is a simple helper for tests with controlled content. In production-grade tests, you may need to handle nested `message/rfc822`, attachments, exceptions, and depth/memory limits if input is untrusted.

Do not use `message.getContent().toString()` to inspect HTML; `getContent()` of a MIME message may be a `Multipart` rather than a `String`.

### 7.4. Special Characters in Subject and Body

Cases that should be covered:

~~~text
Subject: Hóa đơn tháng 11 – tài khoản Nguyễn Ánh
Plain: Xin chào, số tiền thanh toán là 1.250.000 ₫.
HTML: <p>Xin chào Nguyễn Ánh &amp; gia đình!</p>
~~~

For HTML, distinguish between **escaping** and **encoding**:

- UTF-8 handles Unicode characters.
- HTML escaping handles `&`, `<`, and quotes according to rendering context.
- MIME transfer encoding (base64/quoted-printable) is how content is transported over the protocol, not an indication of corrupted data.

Tests should inspect **content after MIME decoding** rather than requiring raw SMTP bytes to contain literal unencoded Vietnamese characters.

## 8. Testing Attachments and Inline Resources

Emails with PDFs, CSVs, or inline logos require additional checks:

~~~java
import org.springframework.core.io.ByteArrayResource;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, true, "UTF-8");

helper.setFrom("invoices@example.test");
helper.setTo("customer@example.test");
helper.setSubject("Test invoice");
helper.setText(
        "The invoice is attached to this email.",
        "<p>The invoice is attached to this email.</p>");

byte[] fakePdf = new byte[] {
        0x25, 0x50, 0x44, 0x46, 0x2D,
        0x31, 0x2E, 0x34, 0x0A
};

helper.addAttachment(
        "invoice-test.pdf",
        new ByteArrayResource(fakePdf),
        "application/pdf");

mailSender.send(message);
~~~

The byte array is merely **dummy data with a PDF-like prefix**, not a valid PDF file that can be opened. Use it when checking filename/content-type attachment handling and transmitting test bytes. If the test needs to open or parse a PDF, use a valid test-controlled PDF fixture.

Recommended assertions:

| Property | Expected |
| --- | --- |
| Filename | `invoice-test.pdf` |
| Content-Type | `application/pdf` or the corresponding media type |
| Attachment count | Matches the expected file count per business rules |
| Bytes | Matches input fixture after decoding |
| HTML/plain text | Still present with accurate content |
| Inline logo | Has a matching `Content-ID` and `cid:...` reference if used |

Do not create multi-megabyte attachments in every unit test. Use small fixtures for frequent tests and separate large-payload tests when verifying timeouts/size limits.

### 8.1. Ordering of setText and addInline

When using inline resources:

~~~java
helper.setText(
        "<html><img src=\"cid:brand-logo\" /></html>",
        true);
helper.addInline(
        "brand-logo",
        new ByteArrayResource(logoBytes),
        "image/png");
~~~

Following common `MimeMessageHelper` usage, setting the text content before adding inline resources ensures the MIME structure is built properly. Integration tests should verify that a mail client or MIME parser can find the `Content-ID` matching the reference in the HTML.

## 9. GreenMail: Receiving Emails via Java API in Tests

Mailpit fits well when you need a container and HTTP API. GreenMail is another option for testing directly inside the JVM, typically letting you retrieve received messages as `MimeMessage` objects.

Java/JUnit test skeleton example:

~~~java
import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetup;
import jakarta.mail.internet.MimeMessage;

import static org.assertj.core.api.Assertions.assertThat;

class GreenMailExample {

    private GreenMail server;

    @BeforeEach
    void startMailServer() {
        ServerSetup setup = new ServerSetup(
                3025, "127.0.0.1", "smtp");
        server = new GreenMail(setup);
        server.start();
    }

    @AfterEach
    void stopMailServer() {
        server.stop();
    }

    @Test
    void capturesMail() throws Exception {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("127.0.0.1");
        sender.setPort(3025);

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("sender@example.test");
        message.setTo("receiver@example.test");
        message.setSubject("Sent to GreenMail");
        message.setText("Test content");

        sender.send(message);

        assertThat(server.waitForIncomingEmail(5000, 1))
                .isTrue();
        MimeMessage[] received = server.getReceivedMessages();
        assertThat(received).hasSize(1);
        assertThat(received[0].getSubject())
                .isEqualTo("Sent to GreenMail");
    }
}
~~~

This is an **in-process server** example that instantiates `JavaMailSenderImpl` directly without starting a Spring context. It tests SMTP transport and received content at the integration level, but does not verify Spring Boot's auto-configuration. Choose a GreenMail artifact/version compatible with `jakarta.mail.*`.

Port `3025` is a fixed example. To run tests reliably in parallel, use dynamic ports or isolate separate servers per test and inject the port into the sender. Avoid test suites competing for the same port. With GreenMail's JUnit 5 extension or Spring context configuration, remember that the server must start **before** the properties creating the mail sender are resolved.

### 9.1. How Does GreenMail Differ from Testcontainers Mailpit?

GreenMail in-process:

- Does not require a Docker runtime.
- Easy access to `MimeMessage` via Java API.
- Can be very fast for small tests.
- Requires managing ports, server lifecycle, and Jakarta Mail compatibility.

Testcontainers Mailpit:

- SMTP service independent of the JVM.
- Infrastructure setup closely resembles a service communicating over a network.
- Easy to inspect emails via UI/API during local debugging.
- Requires a Docker-compatible runtime and container startup time.

No single tool is optimal for every project. A test suite can use **mocks** for unit tests, **GreenMail** for MIME tests, and a **Mailpit container** for end-to-end configuration checks.

## 10. Testing @Async: Waiting on Conditions Instead of Sleep

In a real application, emails may be sent by an `@Async` method:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async("mailExecutor")
    public void sendWelcome(String recipient, String correlationId) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("welcome@example.test");
        message.setTo(recipient);
        message.setSubject("Welcome " + correlationId);
        message.setText("Welcome to the application!");
        mailSender.send(message);
    }
}
~~~

The call to `sendWelcome(...)` may return to the test before the worker finishes sending. Therefore, the following approach is unreliable:

~~~java
welcomeMailService.sendWelcome(recipient, id);
assertThat(mailpitMessages()).hasSize(1);
~~~

At the moment of assertion, the executor may not have processed the job yet.

### 10.1. Using Awaitility to Poll the Mail Server

~~~java
String correlation = UUID.randomUUID().toString();
welcomeMailService.sendWelcome(
        "student@example.test",
        correlation);

await()
        .atMost(Duration.ofSeconds(15))
        .pollInterval(Duration.ofMillis(250))
        .untilAsserted(() -> {
            boolean exists = mailpitApi
                    .findBySubject("Welcome " + correlation)
                    .isPresent();
            assertThat(exists).isTrue();
        });
~~~

`mailpitApi.findBySubject(...)` is a suggested test helper, not a built-in Spring/Mailpit API. It can be built on top of Mailpit's message list endpoint as shown earlier.

Waiting on a **condition with a timeout** is better than a fixed `Thread.sleep`, because:

- Tests do not sleep unnecessarily long when the email arrives quickly.
- Tests have a clear deadline when the worker is stuck.
- CI environments slower than local machines still get a reasonable window.
- It distinguishes a "send failure" from a race between the worker and the assertion.

Do not use a fixed subject across multiple tests running in parallel and assert "any email exists"; a message from another test can cause a false pass.

### 10.2. If @Async Returns CompletableFuture

A service can return `CompletableFuture<MailSubmission>` so callers know when **SMTP submission** has completed:

~~~java
CompletableFuture<MailSubmission> future =
        asyncMailService.submit(command);

MailSubmission submission =
        future.get(10, TimeUnit.SECONDS);

assertThat(submission.deliveryId())
        .isEqualTo(command.deliveryId());
~~~

This pattern is only suitable for tests or boundaries that genuinely need to wait for the result. In a production request path, calling `get()` immediately after `submit(...)` can still force users to wait on SMTP.

Even when the Future succeeds, use a fake mail server to confirm the message was actually received with the expected content and recipient. The service's Future only reflects the service's programmatic logic.

### 10.3. @Async void and Swallowed Errors

With `@Async void`, an exception in the worker is not automatically rethrown to the test thread. A test that merely invokes the method without checking the server/handler may pass even though the SMTP send failed.

In integration tests:

- Use a mail sink to assert the message appears.
- Use an observable `AsyncUncaughtExceptionHandler` if failure testing is needed.
- Better yet, for critical emails, persist job/outbox state and assert that state.
- Do not rely on an HTTP request returning a response to conclude that the email has been sent.

## 11. Testing Transactional Outbox with an SMTP Container

In a commercial application, transactional email sending is often decoupled from the HTTP transaction using a **transactional outbox**:

~~~text
Business service
  |
  | transaction
  +--> save order
  +--> insert mail_outbox(PENDING)
  |
  v
COMMIT
  |
  v
Outbox worker
  |
  +--> claim row (PROCESSING)
  +--> send via JavaMailSender
  +--> mark SENT after SMTP accepted
  |
  v
Mailpit container stores message
  |
  v
Integration test queries DB + Mailpit API
~~~

This is an integration test involving **two systems**:

1. A real database or test container (e.g., PostgreSQL) storing domain and outbox data.
2. An SMTP test container capturing outgoing emails.

Mocking the repository or mail sender separately may miss transaction, concurrency, or connection bugs at this integration boundary.

### 11.1. Testcontainers for PostgreSQL and Mailpit

Multi-container configuration skeleton example:

~~~java
@SpringBootTest
@Testcontainers
class OrderOutboxMailIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>(
                    DockerImageName.parse("postgres:16-alpine"))
                    .withDatabaseName("mail_test")
                    .withUsername("test")
                    .withPassword("test");

    @Container
    static final GenericContainer<?> mailpit =
            new GenericContainer<>(
                    DockerImageName.parse("axllent/mailpit:v1.27.5"))
                    .withExposedPorts(1025, 8025)
                    .waitingFor(
                            Wait.forHttp("/api/v1/messages")
                                    .forPort(8025));

    @DynamicPropertySource
    static void dynamicProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);

        registry.add("spring.mail.host", mailpit::getHost);
        registry.add("spring.mail.port",
                () -> mailpit.getMappedPort(1025));
        registry.add("spring.mail.properties.mail.smtp.auth",
                () -> false);
        registry.add(
                "spring.mail.properties.mail.smtp.starttls.enable",
                () -> false);
    }

    // Autowire application service, outbox repository, and test API.
    // Test executes the use case, then asserts DB state and captured email.
}
~~~

This is a code skeleton; it requires the `org.testcontainers:postgresql` dependency, an appropriate JDBC driver, Spring Data/transaction support, and imports. The project test must create the schema via migrations or controlled test setup.

Image versions are used to **illustrate tag pinning**, which does not imply they are the latest versions. Pick tags verified by your team. Use Testcontainers to test against the actual production database engine when transaction behavior, locking, and SQL dialect matter.

### 11.2. Test: Send Only After Commit

Scenario:

1. Open a business transaction.
2. Save the order and outbox row.
3. Before commit, the worker must not process the email of the uncommitted transaction.
4. After commit, trigger the worker or wait for polling.
5. Verify the outbox transitions from `PENDING` to `SENT`.
6. Verify Mailpit holds one message with the correct correlation ID.

In Spring tests, `@Transactional` on the **test method itself** can cause all created data to commit only after the test finishes (or roll back by default), preventing another worker from seeing the data. Therefore, when testing post-commit outbox flows, explicitly manage the application service's transactions or use `TransactionTemplate`/`TestTransaction` appropriately; **do not wrap the entire test in a rolling-back transaction by default**.

### 11.3. Testing Retries and Idempotency

If a worker retries when a task fails, tests need to distinguish:

- A business event inserts exactly one outbox row (unique `deliveryKey`).
- The worker sends the message and then updates status to `SENT`.
- A subsequent poll does not re-send a message already marked `SENT`.
- Two concurrent workers do not claim the same outbox row while a lease is active.
- If sending throws an explicit error before SMTP acceptance, the outbox transitions to `RETRY`/`FAILED` per policy.
- If the database update to `SENT` fails after SMTP acceptance, there is a risk of duplicates; **do not claim exactly-once**.

Fake SMTP helps verify the actual number of received messages. For instance, a correct workflow can assert `1` message with a unique correlation ID when no crash window is intentionally injected.

### 11.4. Do Not Equate SENT with DELIVERED

If the outbox records:

~~~text
status = SENT
smtpAcceptedAt = ...
~~~

it usually means `JavaMailSender.send` completed - that is, the email was accepted by the SMTP server the application connected to. In an integration test, that SMTP server is **Mailpit**. Do not assert `DELIVERED_TO_INBOX` from Mailpit data because it does not deliver mail to Internet mailboxes.

Testing bounces/DSNs or provider webhooks is a separate test group that requires simulating delivery responses or using an authorized provider staging environment.

## 12. When You Need to Test SMTP Failures

Mailpit/MailHog by default are primarily designed to **receive messages and display their contents**. They are very helpful for happy paths, but do not necessarily offer a full interface for simulating every SMTP failure, such as:

- `421` server temporarily unavailable.
- `450/451` temporary recipient rejection.
- `550/553` permanent rejection.
- SMTP authentication failure.
- Missing STARTTLS or certificate handshake error.
- Connection drop mid-DATA.
- Timeout after the relay has already accepted the message.

Do not assume an SMTP sink can simulate all of these scenarios via simple config flags. You can use:

1. **Mock `JavaMailSender`** to test application-level retry/classification logic.
2. **A scriptable fake SMTP server** for protocol-level failures.
3. **GreenMail with properly configured auth/TLS** for the scenarios it supports.
4. **Provider staging/test mode** if you need to verify a specific vendor response.

### 12.1. Separating Two Failure Types: Preparation vs. Transport

| Failure Type | Examples | How to Test |
| --- | --- | --- |
| MIME preparation | Broken template, invalid address, unreadable attachment resource | Unit test MimeMessageHelper/renderer |
| Executor overload | Task rejected when queue is full | Test with fake or bounded executor |
| SMTP connect timeout | Cannot reach endpoint | Controlled transport failure test |
| SMTP auth failure | Invalid credentials or server requires auth | Auth-enabled fake SMTP or staging |
| SMTP rejection | 4xx/5xx per command | Scripted SMTP server/test harness |
| Database state update failure | Cannot write `SENT` after `send` | Outbox integration test with transaction failure |

Errors during MIME construction happen **before** SMTP sending. If a test only checks that the fake SMTP server has no messages, add assertions on exceptions/state to confirm why no message appeared.

### 12.2. Mockito for Retry Policies

Example testing the dispatcher layer:

~~~java
@Test
void recordsRetryWhenTransportIsTemporarilyUnavailable() {
    JavaMailSender sender = mock(JavaMailSender.class);
    MailOutboxStateService stateService =
            mock(MailOutboxStateService.class);

    doThrow(new MailSendException("SMTP temporary failure"))
            .when(sender).send(any(SimpleMailMessage.class));

    MailDispatcher dispatcher = new MailDispatcher(
            sender,
            stateService,
            new RetryPolicy(/* test config */));

    dispatcher.dispatch(testDelivery());

    verify(stateService).scheduleRetry(
            any(),
            any(),
            eq("SMTP_TEMPORARY"));
}
~~~

`MailDispatcher`, `MailOutboxStateService`, and `RetryPolicy` are **illustrative abstractions** implemented by the application. Creating a `MailSendException` in a mock **does not confirm** that a real SMTP server will return a specific error code; it only tests how the application handles the simulated exception.

Do not classify retryability solely based on the `MailSendException` class name in production: the exception can wrap various failures, including recipient rejections or ambiguous send outcomes.

### 12.3. Network Failures and Timeouts Require Careful Interpretation

A timeout before opening the SMTP connection usually indicates the message was never transmitted. However, if the connection drops after the app has sent DATA, the SMTP server may have already accepted the message even though the client never received the final response.

Retrying immediately in an ambiguous-outcome situation can create duplicates. Integration tests can verify the application's **UNKNOWN-state/reconciliation policy**, but cannot by themselves prove exactly-once semantics between a database and an SMTP server that do not share a transaction.

In tests, do not try to induce random timeouts by making the CI network flaky; use a fake server with deterministic failure behavior and bounded timeouts so tests remain repeatable.

## 13. Data Isolation Between Integration Tests

One test container may be shared across multiple methods in the same test class. If the fake server's mailbox still holds emails from a previous test, assertions like "exactly one email exists" will easily fail on reruns or parallel runs.

Three common strategies:

| Strategy | Pros | Cons |
| --- | --- | --- |
| Dedicated container per test | Strong isolation, minimal noise | Slow, resource-heavy |
| Per-test-class container + clear mailbox | Reuses server within the class | Requires message deletion API and cleanup synchronization |
| Shared container + unique correlation ID | Fewer restarts, faster | Must filter messages accurately, complex concurrency |

There is no single right choice for every test suite. For a handful of email integration tests, a per-class container combined with a unique subject/correlation ID per test is often a practical balance.

### 13.1. Do Not Rely Only on List Position

Avoid:

~~~java
JsonNode first = api.listMessages()
        .path("messages")
        .get(0);
assertThat(first.path("Subject").asText())
        .isEqualTo("Order Confirmed");
~~~

`messages[0]` may belong to another test or the list order may change. Instead, use:

~~~text
deliveryId = UUID generated by test
subject = "Order Confirmed [test:" + deliveryId + "]"
search captured messages by exact subject or correlation header
assert expected recipient + content
~~~

If you want to use a custom header `X-Test-Correlation-ID`, use it only in test environments or when that header is permitted by application policy:

~~~java
mimeMessage.setHeader("X-Test-Correlation-ID", deliveryId);
~~~

The header only helps locate the message; the test still needs to verify that the email belongs to the right recipient and has the expected content.

### 13.2. Clearing the Mailbox Before a Test

If the server API supports deleting messages, you can clear the mailbox in `@BeforeEach` and run the server/test class sequentially. However, with parallel tests sharing a container:

~~~text
Test A: sends message
Test B: clears mailbox
Test A: asserts message exists -> FAIL
~~~

Therefore, **do not use a clear-all endpoint when multiple tests share a mailbox in parallel**. Instead:

- Disable parallel execution for tests sharing a mailbox.
- Or use separate containers/namespaces.
- Or rely exclusively on correlation IDs without deleting other tests' messages.

If cleanup is needed to save memory, perform post-test cleanup in an isolated environment with clear rules.

### 13.3. Avoiding Cached Contexts Pointing to Stopped Containers

The Spring test framework caches application contexts across tests. A class with `@Container static` may stop its container after the class completes, yet the cached context retains a `JavaMailSender` bean pointing to the old host/port if another class improperly reuses that context.

Therefore:

- Group SMTP integration tests with compatible context/container configurations.
- Avoid sharing contexts across classes that have dynamic properties but different server lifecycles.
- When truly needed, use `@DirtiesContext` to prevent inappropriate reuse, at the cost of context restarts.
- Do not reuse a `JavaMailSenderImpl` built with an old container's port expecting it to update itself.
- Do not enable global reusable container mode just for speed if CI isolation/cleanup is not designed for it.

### 13.4. One Test Should Verify One Delivery

When a transaction sends multiple emails, clearly specify what the test is asserting:

~~~text
Create order
  -> customer confirmation: one email to customer
  -> internal audit notice: one email to audit mailbox
~~~

Do not assert that the total message count is `1` if the business logic legitimately produces two emails. Filter by `deliveryId`/recipient/subject and verify each delivery independently.

## 14. Organizing Test Configuration and Avoiding Outbound Mail Leaks

A serious risk is tests accidentally using production SMTP or real credentials when configuration files/profiles are overridden incorrectly.

### 14.1. Separating Configuration by Environment

Example:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-prod.yml

src/test/resources/
  application-test.yml
~~~

`application-test.yml` can specify a local host fallback for tests that do not use Testcontainers:

~~~yaml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 3000
      "[mail.smtp.writetimeout]": 3000
~~~

With Testcontainers, `@DynamicPropertySource` overrides host/port with the container's actual values. Never use production credentials in the test profile.

### 14.2. Using @ActiveProfiles

~~~java
@SpringBootTest
@ActiveProfiles("test")
@Testcontainers
class MailIntegrationTest {
    // Test setup...
}
~~~

This loads test-environment-specific properties. However, **profiles are not the sole security boundary**. Environment variables or command-line arguments have higher precedence and can override test properties if CI accidentally injects `SPRING_MAIL_HOST` or production credentials.

For mail-sending tests:

- Set dynamic host/port from the container via test infrastructure.
- Restrict job network egress where possible.
- Do not grant production SMTP credentials to test jobs.
- Tag integration tests clearly and run them only with an appropriately authorized container runtime.
- Verify per test policy that the mail sender does not point to a production domain.

### 14.3. Fail Closed When Fake SMTP Is Unavailable

A test requiring an SMTP container should **fail clearly** if the Docker daemon is unavailable or the server fails to start. Never silently fall back to real SMTP via another profile or environment secret.

Policy example:

~~~text
Integration test requires SMTP sink
  |
  +-- Container is available -> run test
  |
  +-- Container unavailable -> fail/skip by explicit test policy
      (never fall back to smtp.production.example)
~~~

In CI environments without Docker, you can run unit tests without Testcontainers and isolate integration tests to another job. Never silently turn an integration test into a "mocked success" and claim it tested SMTP.

## 15. Running Testcontainers in CI

To run an SMTP container in CI, the runner needs a compatible container runtime and the necessary permissions for Testcontainers to create/stop containers.

High-level pipeline:

~~~text
Checkout source
       |
       v
Build / compile / unit tests
       |
       v
Start container runtime in CI
       |
       v
Testcontainers starts fake SMTP
       |
       v
Spring Boot test context gets mapped host/port
       |
       v
Run integration tests
       |
       v
Collect test report / sanitized diagnostics
       |
       v
Stop test containers
~~~

Key considerations:

- Pin image tags; avoid relying on `latest` or unexpected network changes.
- Ensure the runner can pull images according to your organization's registry/mirror policies.
- Do not request broader container privileges than needed for testing.
- Do not expose the SMTP test container to the Internet.
- Do not use production test accounts/passwords or send to real recipients.
- Set startup timeouts and assertion timeouts so CI does not hang indefinitely.
- Consider job caching for dependencies/images, but do not cache mailboxes containing sensitive data.
- When running in parallel, budget CPU/RAM/container counts.
- Only export test reports/logs sanitized of credentials/PII.

### 15.1. Splitting Unit and Integration Tests

A pipeline can be split into:

| Job | What It Runs | Requires Docker? |
| --- | --- | --- |
| Unit | Recipient selection logic, model rendering, mock `JavaMailSender` | No |
| MIME test | Building `MimeMessage` with a fake sender | Not necessarily |
| SMTP integration | Spring Mail + Mailpit/Testcontainers | Yes |
| Database + outbox integration | PostgreSQL + SMTP container | Yes |
| Provider staging smoke | Authorized test SMTP/provider configuration | Environment-dependent |

Do not force every developer to run the full provider staging suite on every template tweak. Clear test tags/groups keep feedback fast and costs reasonable.

### 15.2. Testing When Docker Is Unavailable

If you want to keep a real SMTP test path without Docker in the execution environment, you can:

- Start GreenMail/Wiser inside the test JVM.
- Use a fake SMTP service provided by CI on an internal network.
- Run the Testcontainers group on a different, suitable runner.

Never switch to a production provider as a "fallback plan".

### 15.3. Cleanup and Sensitive Data in Captured Mail

Mailpit and other fake servers typically retain copies of email contents. If integration tests send real personal data, the test mailbox also becomes a PII store. Therefore:

- Use only fake recipients, synthetic fixtures, and non-privileged tokens.
- Limit container/volume lifetimes.
- Do not mount a persistent volume containing real test emails unless retention is specifically required.
- Restrict access to the Web UI/API and port mappings.
- Do not save raw EML files of sensitive emails into default CI artifacts.
- Be careful when taking email screenshots for bug reports.

The goal of a test server is to aid testing, not to create another store of production message contents.

## 16. Diagnosing Failures When Integration Tests Fail to Send

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `Connection refused` | Server not started yet or wrong host/port | Wait for readiness, use mapped port |
| `UnknownHostException` | Using hostname `mailpit` when app runs outside Compose | Use the appropriate host per network |
| Testcontainers fails to run | Docker daemon unavailable, wrong permissions/runner | Check CI container runtime configuration |
| Container runs but sends to production SMTP | Incorrect profile/env override | Separate test properties, do not provide production credentials |
| `MailAuthenticationException` | App enables AUTH while fake SMTP does not require/support it as configured | Use `mail.smtp.auth=false` only in isolated test environments |
| STARTTLS error | App requires TLS against an SMTP sink without TLS enabled | Test plain SMTP locally or configure a dedicated TLS-capable fake |
| Timeout despite running server | Firewall/container network, wrong port, or server not ready | Check readiness and verify host/port/runtime |
| `JavaMailSender.send` succeeds but test sees no mail | Reading wrong server/API, async event unfinished, wrong subject filter | Poll by unique correlation ID |
| Flaky tests in parallel runs | Shared mailbox, clear-all, fixed port | Container/test isolation, dynamic ports |
| Message exists but subject renders weirdly | Encoding/charset issue or asserting raw header | Decode MIME properly |
| Plain text disappears | Helper only sets HTML or unexpected MIME nesting | Use `setText(plain, html)`, traverse MIME tree |
| Attachment unreadable | Non-reopenable stream resource or invalid fixture | Use `ByteArrayResource`/repeatable resource |
| Fails on old port after running another class | Spring context cache points to stopped container | Manage lifecycle/caching or use `@DirtiesContext` |
| Passes intermittently with async emails | Asserting before worker finishes processing | Wait conditionally with a timeout |
| Test sends duplicates automatically | Worker/outbox retry, duplicate event, or concurrent polling | Check idempotency/leases and count by delivery ID |

### 16.1. Connection Refused and Port Mapping

In Testcontainers, do not write:

~~~java
registry.add("spring.mail.host", () -> "localhost");
registry.add("spring.mail.port", () -> 1025);
~~~

because `1025` is only the port **inside the container**. Replace with:

~~~java
registry.add("spring.mail.host", mailpit::getHost);
registry.add("spring.mail.port",
        () -> mailpit.getMappedPort(1025));
~~~

This is one of the most common mistakes when migrating from local Docker Compose to Testcontainers.

### 16.2. Do Not Leave SMTP Debug On Indefinitely

When testing SMTP protocol errors, you can enable debug logging in a controlled test environment, but you do not need and should not enable detailed authentication logs in production. Jakarta Mail debug output or application logs can contain email addresses/headers, and depending on configuration may expose sensitive information.

When debugging:

1. Use test credentials and test addresses.
2. Limit duration and log storage locations.
3. Do not print SMTP passwords/tokens.
4. Inspect exception causes and classified error codes.
5. Disable debug logging when finished.

A test container helps diagnose issues without enabling real provider logs or sending emails externally.

## 17. Testing a Real Business Flow: Account Registration Confirmation

Consider an application that sends a welcome email when a user completes registration. An integration test can combine the Spring application service, database, and Mailpit.

### 17.1. Business Outcomes to Verify

Assume the requirements:

1. User registers successfully.
2. The application records an intent to send a welcome email.
3. The worker uses a template to render HTML/plain text.
4. The test SMTP server accepts the email.
5. The content must include the recipient's name and a valid verification URL in the test environment.

Flow:

~~~text
POST /registrations
       |
       v
RegistrationService
  +--> save user
  +--> save mail outbox
       |
       v
   DB commit
       |
       v
 MailOutboxWorker
       |
       v
Thymeleaf template + MimeMessageHelper
       |
       v
JavaMailSender
       |
       v
Mailpit SMTP port (mapped dynamically)
       |
       v
Mailpit API: captured email
       |
       v
Test asserts:
  - account created
  - outbox transitioned correctly
  - exactly expected captured messages
  - To/subject/body/URL correct
~~~

Use isolated test data and never use real verification tokens with production privileges. If the URL contains a test-only token, you can assert **valid path and format** without printing the token into test reports.

### 17.2. Using a Correlation ID to Find the Right Message

A common pattern:

~~~java
String uniqueEmail =
        "student+" + UUID.randomUUID() + "@example.test";

registrationService.register(
        new RegistrationCommand(
                uniqueEmail,
                "Nguyễn An"));

await()
        .atMost(Duration.ofSeconds(15))
        .untilAsserted(() -> {
            var captured = mailpitApi.findByRecipient(uniqueEmail);
            assertThat(captured).hasSize(1);
            assertThat(captured.get(0).subject())
                    .contains("Welcome");
            assertThat(captured.get(0).plainText())
                    .contains("Nguyễn An");
        });
~~~

`registrationService.register`, `mailpitApi.findByRecipient`, and the models in the example are **design-oriented test pseudocode**, not built-in Spring APIs. Implement the test client against Mailpit's schema and your application's business domain.

If a valid registration sends multiple emails, assertions must specify which email type is being checked rather than simply counting all messages to that address.

### 17.3. Verifying No Email Is Sent on Transaction Rollback

An important scenario:

~~~text
Begin registration transaction
    |
    +--> save user
    +--> save outbox
    |
    v
Business validation fails
    |
    v
ROLLBACK
    |
    v
No committed outbox row
    |
    v
No email submitted to Mailpit
~~~

If the application invokes `@Async` or sends directly **before the transaction commits**, the email may already be received by the fake server even though the transaction ultimately rolls back. This is an integration bug that unit tests mocking only the mail sender may miss in a real transactional context.

The test should verify:

- A failed transaction creates no committed outbox row.
- The worker does not send mail for an uncommitted event.
- No captured message corresponds to the unique registration ID.

When testing for the **absence of an email**, do not merely check immediately and pass: an async worker could run afterwards. Use explicit worker/queue synchronization, wait for an observation window per the test SLA, or trigger polling deterministically to prove no eligible job was dispatched.

### 17.4. Verifying Retries Do Not Cause Duplicate Sends on the Happy Path

After a delivery has transitioned to `SENT`:

1. Trigger the worker poll again.
2. Verify no new SMTP submission occurs for the same delivery.
3. Verify the delivery/outbox remains in the expected terminal state.
4. Verify the database does not create a new outbox row for the same business event if deduplication is required.

This tests application idempotency under normal conditions. It does not prove **exactly-once when the JVM crashes after SMTP acceptance**; that case still leaves a duplicate window if the provider does not support idempotency.

## 18. Additional Scenarios to Test Beyond the Happy Path

A quality integration test suite should not contain only "send one message successfully". Define test cases according to product requirements:

| Scenario | Appropriate Test Level | Expected Result |
| --- | --- | --- |
| Simple plain text | SMTP sink | Server captures accurate From/To/subject/body |
| HTML + plain alternative | MIME + SMTP sink | Both content parts exist and decode properly |
| Vietnamese/Unicode | MIME + SMTP sink | Subject/body have no encoding corruption |
| Attachment/inline image | MIME + SMTP sink | Filename, content type, bytes/CID are accurate |
| Single recipient | SMTP sink | Only the authorized recipient receives it |
| Cc/Bcc | MIME + SMTP sink | Envelope recipients are right and Bcc is not unintentionally exposed in headers |
| Invalid recipient format | Unit/MIME | Rejected or flagged at the appropriate layer |
| SMTP 4xx | Scripted SMTP/mock | Retries with backoff and max attempts |
| SMTP 5xx | Scripted SMTP/mock | Appropriate permanent failure/suppression policy |
| SMTP connect timeout | Controlled failure test | Reports transport failure without hanging indefinitely |
| Mandatory AUTH/TLS | Auth/TLS-capable fake or staging | Never sends credentials over an unauthorized channel |
| `@Async` worker | SMTP sink + Awaitility | Message appears within the allowed timeout |
| Transaction rollback | DB + SMTP sink | No email sent for rolled-back event |
| Outbox retry/success | DB + SMTP sink | Valid state and message count |
| Two workers claiming concurrently | DB integration | Cannot both claim one row while lease is active |
| Duplicate business event | DB + SMTP sink | Does not emit multiple deliveries if dedup policy forbids |
| Shutdown/restart mid-job | DB/outbox integration | Unfinished job recovers per policy |
| Post-send feedback/bounce | Provider webhook simulator/DSN fixture | Updates delivery status, not confused with SMTP acceptance |

### 18.1. Checking Bcc

`Bcc` has a special property: the recipient belongs to the delivery envelope, but outgoing headers must not expose the Bcc list. When using an SMTP test sink, you may need to verify both:

- Recipients the server received in the SMTP envelope.
- Headers of the serialized message.

Checking only the `To` header or Web UI may not suffice to prove Bcc was handled properly. Use a test server/harness that lets you inspect envelope recipients and confirm Bcc was not accidentally turned into `To`/`Cc`.

### 18.2. Testing Size Limits

A large email with attachments can:

- Consume significant memory during MIME construction and encoding.
- Be rejected by the SMTP server due to SIZE limits.
- Exceed application timeouts/bandwidth.

Tests can use an appropriately sized fixture and a mock environment with a predefined limit. Do not generate hundreds of megabytes of data in tests that run on every commit if you only need to verify a limit policy; isolate performance/size tests.

### 18.3. Testing TLS/AUTH Differs from an Unsecured SMTP Sink

Locally, `mail.smtp.auth=false` and STARTTLS disabled are convenient settings for content testing. They do not prove the production application uses TLS securely.

If TLS/AUTH integration is required, use:

- A fake SMTP server supporting AUTH/STARTTLS or implicit TLS.
- Dedicated test certificates and a separate test truststore.
- Tests verifying handshake failure when the server certificate is untrusted.
- Fail-closed tests when the server does not support STARTTLS while the client requires it.
- An authorized staging provider with credentials not shared with production.

**Never use `mail.smtp.ssl.trust=*` or disable hostname verification in production** just to make tests pass. If using a self-signed truststore in tests, configure a separate test truststore and never carry permissive trust policies into real environments.

## 19. Test Slices and Spring Boot Auto-Configuration

A common mistake is writing a unit test that manually instantiates `JavaMailSenderImpl` and assuming Spring Boot's auto-configuration has been tested.

Example:

~~~java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost(mailpit.getHost());
sender.setPort(mailpit.getMappedPort(1025));
~~~

This call **does not prove** Spring bound `spring.mail.host`, `spring.mail.port`, and SMTP properties as intended.

If you want to verify application configuration:

~~~java
@SpringBootTest
@Testcontainers
class MailAutoConfigurationIT {

    @Autowired
    JavaMailSender mailSender;

    // @Container + @DynamicPropertySource as in the previous section.

    @Test
    void sendsUsingBootConfiguredSender() {
        // Use the bean injected by Spring.
        // Assert the result in the SMTP sink via the test API.
    }
}
~~~

This style of test has higher startup overhead, but verifies that the **Spring container, bean selection, property binding, and SMTP transport** work together.

### 19.1. When Multiple JavaMailSender Beans Exist

An application may configure multiple senders for transactional, support, or marketing mail. If multiple beans of the same type exist, injection without `@Qualifier` may be ambiguous, or the test may send through a different sender than the business flow under test.

The test must specify:

~~~java
@Autowired
@Qualifier("transactionalMailSender")
JavaMailSender transactionalSender;
~~~

If custom senders are configured in the application, `spring.mail.*` may not automatically apply to manually created beans unless the configuration code binds them. Testing with the real bean helps catch mismatches between auto-configuration and custom configuration.

### 19.2. Fake Transport Does Not Replace Template Testing

If a Spring service uses Thymeleaf/FreeMarker or a custom renderer, tests connecting to fake SMTP should use the **real renderer** for at least one sample email. Replacing the template engine with a mock in integration tests prevents catching wrong variable keys or HTML rendering failures.

However, individual template content tests can live in a separate test class without starting a container every time. Keep a few representative end-to-end tests rather than repeating every template test against an SMTP container.

## 20. Test Suite Performance and Stability

Testcontainers helps reproduce environments, though it also consumes time and resources. Good practices include:

- Tag integration tests clearly so CI can run them after unit tests.
- Use a per-class container or a managed test fixture with a clear lifecycle.
- Only spin up a database+SMTP combo for tests requiring real transaction boundaries.
- Avoid long `Thread.sleep` calls; use readiness checks and Awaitility.
- Bound server/container startup timeouts according to the CI environment.
- Use correlation IDs so tests can rerun without colliding with old messages.
- Never auto-clear a shared mailbox while parallel tests are running.
- Use small, deterministic fixtures containing no real data.
- When a test fails, report the correlation ID/error category without printing the entire email body.

### 20.1. Avoid Arbitrary Global Singleton Containers

A single container for the entire test suite can cut startup time, but can also cause:

- Leftover messages across classes.
- Cross-test interference during parallel execution.
- Spring context cache holding stale host/port values.
- Difficult cleanup after a test class fails.

If opting for a singleton, establish clear test infrastructure for lifecycle, isolation, and context mapping. Do not treat `withReuse(true)` as a default fix for every slow test.

### 20.2. Do Not Assert Against Absolute Wall-Clock Time

The following example is prone to flakiness:

~~~java
assertThat(mailpitLastMessageReceivedAt())
        .isEqualTo(Instant.now());
~~~

Arrival time has latency, clock/timezone differences, and precision limits. Better approaches:

- Assert the message has the exact correlation ID.
- Check that the timestamp falls within a reasonable range if needed.
- Use an injected `Clock` for deadline/retry logic.
- Use events/polling with timeouts rather than relying on fixed millisecond offsets.

## 21. Frequently Asked Questions

**"Is mocking `JavaMailSender` enough to test email sending?"**  
It is sufficient for some unit tests covering business logic and invocation counts, but it does not verify the SMTP connection, MIME serialization, or that the server received the right message. You should have at least one integration test with fake SMTP for critical sending paths.

**"How does Mailpit differ from MailHog?"**  
Both can act as an SMTP sink and provide a UI/API for inspecting messages. They differ in implementation, APIs, capabilities, and project lifecycle. Pick the tool that fits your infrastructure and target the API of your exact version; do not assume identical endpoints or schemas.

**"Does GreenMail require Docker?"**  
When running GreenMail in-process from Java/JUnit, Docker is not required. GreenMail can also be run as a standalone/container model depending on needs. Choose an artifact compatible with your application's Jakarta Mail/JavaMail version.

**"Does an SMTP sink send emails to real Gmail or Outlook accounts?"**  
Normally no; a sink's purpose is to receive and retain mail within the test environment. If you see real emails leaving the system, immediately check host/port and network policies because the test may accidentally be using a real SMTP provider.

**"Does Testcontainers require docker-compose.yaml?"**  
Not necessarily. For instance, `GenericContainer` can start directly from an image via Testcontainers. Docker Compose fits local development; Testcontainers fits JUnit-managed lifecycles.

**"Why does the container use port 1025 while Spring must use a different port?"**  
`1025` is the port inside the container; Testcontainers exposes it on a dynamically allocated host port. The test application must use `getMappedPort(1025)` and `getHost()`.

**"Should we always use a fixed port 1025 for every test?"**  
No, especially if running multiple test instances/containers in parallel. Dynamic ports avoid conflicts and are generally better suited for CI.

**"How does Spring Boot read Testcontainers host/port?"**  
`@DynamicPropertySource` supplies properties to the Spring test context before beans are created. You can register `spring.mail.host` and `spring.mail.port` based on the container.

**"Is @ActiveProfiles(test) enough to guarantee no emails go to real SMTP?"**  
No. Environment variables or other property sources can override the test profile. Always supply host/port from the container and deny CI integration jobs access to production credentials.

**"Why did `send(...)` succeed yet the test cannot find the message?"**  
You may be querying the wrong server/API, using an incorrect subject filter, hitting another container, or checking before an async operation finished. Use a unique correlation ID, polling with timeout, and verify mapped ports.

**"Should we use Thread.sleep to wait for emails?"**  
Not as the primary mechanism. `Awaitility` or conditional polling with a timeout is generally more reliable and faster when emails arrive early.

**"Does Mailpit receiving an email mean it was delivered to a real inbox?"**  
No. It only confirms the test SMTP sink received the message. Real deliverability also depends on the mail provider, DNS, reputation, spam filtering, destination server, and bounce handling.

**"Why do HTML emails appear broken when tests only call getContent().toString()?"**  
`MimeMessage.getContent()` can return a `Multipart`. You need to traverse the MIME tree and decode the `text/html` or `text/plain` part properly.

**"Do we need to compare raw MIME byte-for-byte?"**  
Usually not. MIME boundaries, Date, and Message-ID can legitimately vary. Assert the properties and content meaningful to the business logic.

**"What should we assert when testing Vietnamese over SMTP?"**  
Check the subject and body **after MIME decoding**, ensuring Vietnamese diacritics and special characters are intact. Do not require the raw wire format to display literal Unicode, as messages may use quoted-printable/base64.

**"Can GreenMail retrieve MimeMessage directly?"**  
Yes, via GreenMail's corresponding API, making it easy for tests to assert subject/MIME trees. The GreenMail version must be compatible with Jakarta Mail in your application.

**"Can default Mailpit be used to test SMTP 550 errors?"**  
Do not assume so. An SMTP sink primarily receives messages; to test 4xx/5xx/auth/TLS, you may need a scriptable fake SMTP server, properly configured GreenMail, or provider staging.

**"Should we mock MailSendException to test retries?"**  
Yes, when the goal is to test the application's retry/backoff logic. However, a mock does not prove a real server will produce that exact exception/cause in a specific protocol scenario.

**"Can an SMTP container be used to test @Async?"**  
Yes. Call the real async service and poll the server or outbox state until the condition is met with a timeout. Do not expect `@Async void` to propagate exceptions directly back to the test thread.

**"Does outbox SENT mean the email reached the inbox?"**  
If `SENT` is defined as successful SMTP submission, then no. In integration tests, it only proves the fake SMTP accepted the message. Delivery/bounce status must be tracked separately.

**"Should Testcontainers run on every pull request?"**  
It depends on cost and quality requirements. It is generally beneficial to run a critical integration test group in CI with a container runtime, while faster unit tests run on every change.

**"Should we use the :latest image tag?"**  
In CI requiring reproducibility, pin a tag/digest verified by your team. You can proactively upgrade the image on a schedule and rerun tests.

**"Do we need SMTP login on local Mailpit?"**  
A basic local SMTP sink typically does not require SMTP AUTH. If using `auth=false`, apply it only to isolated test environments; production must follow the provider's authentication and TLS policies.

**"What if CI has no Docker?"**  
Move the Testcontainers group to a different runner, or use in-process GreenMail/Wiser for tests that can be covered that way. Never fall back to production SMTP.

**"Is Mailpit enough when testing bounces?"**  
Not necessarily. Default SMTP sinks do not deliver over the Internet and thus do not simulate full bounces/DSNs. You can use DSN fixtures, webhook simulators, or a staging mail relay/provider capable of generating error responses.

## 22. Design and Implementation Checklist for SMTP Integration Tests

### Testing Objectives

1. Clarify whether the test verifies business logic, MIME, SMTP acceptance, or provider deliverability.
2. Do not use mocks as proof that a real SMTP server received a message.
3. Choose Mailpit/MailHog, GreenMail, or another test server based on the capabilities actually needed.
4. Test at least one happy path going through Spring's real `JavaMailSender` bean.

### Configuration and Environment

5. Use test/local profiles separate from production.
6. Do not supply production SMTP passwords to test jobs.
7. With Testcontainers, use `getHost()` and `getMappedPort(...)`.
8. Use `@DynamicPropertySource` or an equivalent test property mechanism before Spring creates the sender.
9. Pin verified image/dependency versions.
10. Wait for container readiness before running assertions.
11. Do not expose the SMTP sink/API to public networks.
12. If Docker is unavailable, fail/skip according to an explicit test policy; never send to a real provider.

### Email Content

13. Verify recipient/From/Reply-To/subject accuracy.
14. Verify Unicode/UTF-8 of subject and body after MIME decoding.
15. If both HTML and plain text are present, verify both variants.
16. For attachments/inline resources, verify filename, media type, bytes, and CID.
17. Use synthetic data and fake tokens; never put production PII into test mailboxes.

### Repeatability and Reliability

18. Give each test a unique correlation ID or unique subject/recipient.
19. Use polling with timeouts instead of fixed sleeps when testing asynchronously.
20. Never clear a shared mailbox while other tests are running.
21. Manage container lifecycles, Spring context caching, and parallel execution.
22. Do not assert raw MIME byte-for-byte when variable parts like boundary/date do not matter.
23. Test transaction rollback/outbox along real commit boundaries.
24. Separate synchronous SMTP failures, async job failures, and database state-write failures.

### Safety and Operations

25. Configure SMTP timeouts so tests do not hang indefinitely.
26. Do not enable SMTP auth/debug logs containing secrets in CI.
27. Do not include sensitive raw emails in test reports/artifacts.
28. Stop/clean up containers after tests according to an appropriate lifecycle.
29. Maintain a separate test group for TLS/AUTH/provider-specific failures if required.
30. Never treat SMTP sink tests as proof of SPF/DKIM/DMARC or inbox delivery.

## 23. Tool Selection Decision Diagram

~~~text
Need to test email sending?
            |
            v
Only need send-call logic / passed data?
            |
      +-----+-----+
      |           |
     Yes         No
      |           |
      v           v
Mockito/mock   Need MIME/charset/attachment?
                  |
            +-----+-----+
            |           |
           Yes         No
            |           |
            v           v
     MimeMessage     Need SMTP network/protocol?
     direct test           |
                       +--+--+
                       |     |
                      Yes   No
                       |     |
                       v     v
                Fake SMTP    Appropriate unit test
                       |
               +-------+--------+
               |                |
           Have Docker?      No Docker?
               |                |
               v                v
      Mailpit/Testcontainers  GreenMail/Wiser
               |
               v
      Need DB transaction/outbox?
               |
         +-----+-----+
         |           |
        Yes         No
         |           |
         v           v
   DB container +  Standalone
   SMTP container  SMTP container
~~~

This is a suggestion for choosing tools by primary goal; GreenMail can also run in a container, and Mailpit can run as a local process. Do not restrict any tool to a single deployment model.

## 24. Summary of the Spring Framework Mail Testing Flow

A balanced testing architecture can be organized as:

~~~text
                           Unit tests
                               |
               +---------------+----------------+
               |                                |
               v                                v
      Business logic + mock              MIME builder/renderer
      JavaMailSender call                charset / text / HTML
               |                                |
               +---------------+----------------+
                               |
                               v
                       Integration tests
                               |
                               v
                 Spring Boot JavaMailSender
                               |
                               v
                   SMTP fake/test container
                               |
                               v
                      Captured messages
                               |
                               v
                API/Java assertion with unique ID
                               |
                  +------------+------------+
                  |                         |
                  v                         v
           Message correctness      @Async/outbox/DB state
                  |                         |
                  +------------+------------+
                               |
                               v
                    Separate provider staging
                    when production-like TLS,
                    auth or deliverability is needed
~~~

**Key takeaways:**

- **Mock senders** verify interactions; **fake SMTP** verifies transport and captured messages.
- **Mailpit/MailHog** are convenient for local and Testcontainers; **GreenMail** is useful when a Java API or in-process server is needed.
- In Testcontainers, use **dynamic mapped host/port**, never hard-code the host port.
- For HTML, attachment, and Vietnamese emails, inspect **decoded MIME**, not just `send` call counts.
- For `@Async`, use **conditional polling with timeouts** and correlation IDs; for outbox, test both transactions and states.
- **SMTP accepted is not inbox delivered**; bounces/DSNs and provider specifics need separate tests.
- Isolate test SMTP from the Internet and production credentials to prevent accidental sends and data leaks.

## Conclusion

**A fake mail server or SMTP test container** is an essential component for Spring Framework Mail integration testing. It allows the application to use the real `JavaMailSender`, establish real SMTP connections, and inspect actual captured messages in a controlled environment. As a result, teams can catch host/port configuration issues, MIME bugs, Unicode issues, attachment problems, async flows, and outbox bugs before deployment.

A practical design typically starts with **unit tests with mocks**, adds **MIME tests**, and then uses **Mailpit/Testcontainers or GreenMail** for critical sending flows. When provider specifics, TLS/AUTH, or deliverability need verification, maintain a dedicated, authorized staging test layer. This layered strategy provides fast feedback, repeatable results, and minimizes the risk of accidentally sending real emails during development and CI.
