# Mocking JavaMailSender According to the Contract Under Test

A Spring Boot service sends an order confirmation email. The developer creates a mock `JavaMailSender`, calls the service method, and asserts `verify(sender).send(any(MimeMessage.class))`. The test passes, yet in production recipients see no subject, HTML emails lack a plain-text part, or attachments have the wrong filename. The reason is that the test only verified **an API invocation**, without verifying **the contract the service is responsible for**.

Another scenario: the service calls `JavaMailSender.send(MimeMessagePreparator)` and passes a lambda to build the message. By default, a Mockito mock **does not execute the preparator lambda**. The test still passes if you only verify `send(...)` was called, even when the MIME-building code inside the lambda is broken. This is an especially important pitfall when mocking `JavaMailSender`.

This lesson belongs to the **Unit Testing** chapter of **Spring Framework Mail**. The goal is not to simulate an SMTP server inside Mockito. The goal is to set proper unit-test boundaries, mock the right `JavaMailSender` methods, inspect the values and MIME structure the application promises to produce, test error branches, and avoid confusing a mock invocation with successful mail delivery.

## 1. What is the contract under test?

A **contract** in unit testing is the observable behavior one component is responsible for guaranteeing to another. For a mail service, the contract may include:

- **Recipients:** sending to the exact one or more validated addresses.
- **Sender:** using the configured and authorized From address.
- **Subject:** the right subject for the notification type and business facts.
- **Content:** plain text, HTML, encoding, and values escaped appropriately for the context.
- **Attachments:** right filename, Content-Type, and byte content when the use case requires them.
- **Submission call count:** one submission call per action within unit-test scope.
- **Error handling:** never swallowing errors or confusing message-preparation errors with send errors.
- **Not sending when invalid:** bad data, recipient suppressed by business policy, or notification that should not be emitted.

Not every contract belongs to `JavaMailSender`. For example, "one domain event creates only one notification intent" belongs to the application/outbox layer and must be tested at a different boundary; "email reaches the Inbox" belongs to delivery and cannot be proven with Mockito.

### 1.1. Three distinct testing layers

| Layer | Subject under test | Appropriate tools | Cannot prove |
|---|---|---|---|
| **Application/mail service unit test** | Data passed to `JavaMailSender`, validation, exception handling, call count | Mockito + JUnit, real in-memory `MimeMessage` when needed | SMTP server availability, Inbox delivery |
| **Mail adapter integration test** | MIME serialization, SMTP protocol, TLS/AUTH, interaction with test server | GreenMail, Mailpit, or compatible SMTP catcher | Inbox placement at real providers |
| **End-to-end/operational test** | Submission via ESP, bounces/webhooks, authentication, provider events | Test accounts/providers, test mailboxes, monitoring systems | Guaranteeing every future email lands in Inbox |

**Mockito replaces the collaborator of the code under test; it does not replace the SMTP protocol.**

### 1.2. Test behavior rather than locking down implementation

Suppose the business requirement is "send a confirmation email to the customer's address with the right subject and clear content." Whether the service names a local variable `message` or `mail` is not part of the contract.

A useful unit test verifies recipient, subject, body, and one `send` invocation. A test overly coupled to implementation details may fail when refactoring how `MimeMessageHelper` is constructed without changing a single thing the recipient sees.

Conversely, `verify(sender).send(any(...))` alone is too weak because it ignores all meaningful data.

## 2. JavaMailSender has multiple overloads: mock the right path

`JavaMailSender` in Spring supports several sending signatures, including:

```java
void send(SimpleMailMessage simpleMessage) throws MailException;
void send(SimpleMailMessage... simpleMessages) throws MailException;

void send(MimeMessage mimeMessage) throws MailException;
void send(MimeMessage... mimeMessages) throws MailException;

void send(MimeMessagePreparator mimeMessagePreparator)
        throws MailException;
void send(MimeMessagePreparator... mimeMessagePreparators)
        throws MailException;

MimeMessage createMimeMessage();
MimeMessage createMimeMessage(InputStream contentStream)
        throws MailException;
```

This list illustrates methods on the Spring Mail interface/API; `SimpleMailMessage` belongs to the `MailSender` API that `JavaMailSender` extends. Methods with similar names yet different parameter types represent **different invocation contracts**.

| Code in service | What to observe/test? | Common pitfall |
|---|---|---|
| `sender.send(SimpleMailMessage)` | `SimpleMailMessage` and its field getters | A `MimeMessage` captor will not capture this message |
| `sender.createMimeMessage(); sender.send(MimeMessage)` | Stub `createMimeMessage()` to return a real `MimeMessage`, capture `send(MimeMessage)` | Mocking `MimeMessage` causes helper calls to write to a dummy object with no content |
| `sender.send(MimeMessagePreparator)` | Capture and **execute the preparator** on a real `MimeMessage` or use `doAnswer` | Mockito does not run the lambda by default |
| `sender.send(SimpleMailMessage[])` | Capture the message array, check count and each element's data | Verifying `send(any(SimpleMailMessage.class))` targets the wrong overload |
| `sender.send(MimeMessage[])` | Inspect messages in the array and each MIME structure | Checking only one element can miss partial/batch behavior |

### 2.1. Why does Mockito make overload confusion easy?

Java selects overloads at **compile time** based on argument types; Mockito likewise uses matcher/captor types to pick which method is verified.

For example:

```java
verify(sender).send(any(MimeMessage.class));
```

only checks that specific `MimeMessage` path; it does not automatically verify `send(SimpleMailMessage)` or `send(MimeMessagePreparator)`.

Declare typed matchers explicitly:

```java
verify(sender).send(any(SimpleMailMessage.class));
verify(sender).send(any(MimeMessage.class));
verify(sender).send(any(MimeMessagePreparator.class));
```

Each line belongs to a different scenario; do not copy all three into one test when the service uses only one overload.

### 2.2. send methods return void

Never write:

```java
when(sender.send(any(MimeMessage.class))).thenReturn(true);
```

Because `send` returns `void`, Mockito cannot use `when(...).thenReturn(...)` on it.

To simulate a failure, use:

```java
doThrow(new MailSendException("SMTP unavailable"))
        .when(sender)
        .send(any(MimeMessage.class));
```

To simulate executing a callback, use `doAnswer(...)`. For a normal happy path, a `void` mock already does nothing; `doNothing()` is usually unnecessary.

## 3. Tools and test structure

The examples use:

- Java 17+ with text block/record syntax where needed.
- Spring Framework Mail with `JavaMailSender`, `SimpleMailMessage`, and `MimeMessageHelper`.
- Jakarta Mail namespace `jakarta.mail.*` matching modern Spring Framework.
- JUnit Jupiter.
- Mockito with `MockitoExtension`.
- AssertJ for readable assertions.

Gradle dependency example using Spring Boot and the test starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is an illustrative declaration, not a command to execute in this lesson. Actual versions are governed by your project's BOM/dependency management. Legacy Spring projects use `javax.mail.*` instead of `jakarta.mail.*`; do not mix the two namespaces in the same example.

### 3.1. Tests do not need to start a Spring context

A constructor-injected mail service class can be tested with:

```java
@ExtendWith(MockitoExtension.class)
class RegistrationMailServiceTest {

    @Mock
    JavaMailSender sender;

    RegistrationMailService service;

    @BeforeEach
    void setUp() {
        service = new RegistrationMailService(
                sender,
                "notifications@example.com");
    }
}
```

Typical imports:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.javamail.JavaMailSender;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
```

This approach needs no `@SpringBootTest`, no `application.yml`, no network connection, and usually runs quickly. Test fixtures pass the From value directly instead of reading environment variables.

### 3.2. Constructor injection keeps testing clean

If a service instantiates `new JavaMailSenderImpl()` inside a method, swapping out the sender for testing becomes difficult. Keep the sender as an injected dependency:

```java
public final class RegistrationMailService {

    private final JavaMailSender sender;
    private final String fromAddress;

    public RegistrationMailService(
            JavaMailSender sender,
            String fromAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
    }

    // Business-facing methods below.
}
```

Production can bind the From address from configuration:

```java
public RegistrationMailService(
        JavaMailSender sender,
        @Value("${app.mail.from}") String fromAddress) {
    this.sender = sender;
    this.fromAddress = fromAddress;
}
```

In unit tests, invoke the constructor with a fixed address; there is no need to boot a Spring container just to inject configuration.

## 4. Test SimpleMailMessage: capture the actual sent data

For simple plain-text emails, `SimpleMailMessage` is the right API. Keep the service small enough to test the contract cleanly.

### 4.1. Example service

```java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class RegistrationMailService {

    private final JavaMailSender sender;
    private final String fromAddress;

    public RegistrationMailService(
            JavaMailSender sender,
            String fromAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
    }

    public void sendWelcome(String recipient, String displayName) {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient is required");
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setTo(recipient);
        message.setSubject("Welcome to the system");
        message.setText(
                "Hello " + displayName
                + ", your account is ready.");

        sender.send(message);
    }
}
```

This service does not speak SMTP directly; `JavaMailSender` is an injected collaborator.

### 4.2. Use ArgumentCaptor

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.times;

@ExtendWith(MockitoExtension.class)
class RegistrationMailServiceTest {

    @Mock
    JavaMailSender sender;

    RegistrationMailService service;

    @BeforeEach
    void setUp() {
        service = new RegistrationMailService(
                sender, "notifications@example.com");
    }

    @Test
    void sendsWelcomeWithCorrectPlainTextContract() {
        service.sendWelcome("lan@example.net", "Lan");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender, times(1)).send(captor.capture());

        SimpleMailMessage actual = captor.getValue();

        assertThat(actual.getFrom())
                .isEqualTo("notifications@example.com");
        assertThat(actual.getTo())
                .containsExactly("lan@example.net");
        assertThat(actual.getSubject())
                .isEqualTo("Welcome to the system");
        assertThat(actual.getText())
                .contains("Hello Lan")
                .contains("your account is ready");
    }
}
```

This test verifies:

1. The service requests sending one `SimpleMailMessage`.
2. Sender and recipient data are correct.
3. Subject and body satisfy the contract.
4. No real SMTP call occurs because `sender` is a mock.

### 4.3. Why not just verify(any)?

Too weak of a test:

```java
service.sendWelcome("lan@example.net", "Lan");
verify(sender).send(any(SimpleMailMessage.class));
```

It will stay green even if the service sets `To` to another address, leaves the subject empty, or omits the recipient's name from the body. `ArgumentCaptor` checks meaningful values, not just that a call occurred.

### 4.4. Test the "must not send" case

```java
@Test
void doesNotSendWhenRecipientBlank() {
    assertThatThrownBy(
            () -> service.sendWelcome(" ", "Lan"))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("Recipient");

    verifyNoInteractions(sender);
}
```

Because validation happens before creating or calling the sender, this test proves an input missing a recipient is blocked at the proper boundary. In a real application, more thorough email address validation may be needed at the application boundary; do not treat `isBlank()` as full RFC validation or mailbox existence verification.

### 4.5. Verify exact call count, yet do not infer distributed exactly-once

`times(1)` verifies that during **one unit test execution**, the service called the mock once. It does not prove HTTP retries, broker redeliveries, or multiple workers will not produce duplicate notifications.

Guaranteeing that one event produces only one send request in a distributed system requires idempotency keys, unique constraints/outbox tables, and persistence-layer integration tests.

## 5. Mockito mocks JavaMailSender, yet MimeMessage should be real

`MimeMessage` carries real data logic: headers, charsets, MIME parts, Content-Type, multipart boundaries, and attachments. If you mock `MimeMessage` too, calls such as `MimeMessageHelper.setText(...)` only invoke no-op methods on the mock, leaving no real content to inspect.

Useful pattern:

- **Mock** `JavaMailSender` to prevent real transport calls.
- **Create a real in-memory `MimeMessage`** using a `jakarta.mail.Session` without SMTP configuration.
- **Capture** the exact `MimeMessage` passed to `send`.
- **Read** fields and MIME parts using the Jakarta Mail API.

### 5.1. Create a MimeMessage without opening the network

```java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;

import java.util.Properties;

MimeMessage realMessage =
        new MimeMessage(Session.getInstance(new Properties()));
```

`Session.getInstance(new Properties())` creates a JavaMail session for building/reading messages in memory. Creating this object **does not connect to an SMTP server**. Network access only happens if a test explicitly opens a transport or calls a real sender configured with network settings.

### 5.2. Stub createMimeMessage()

```java
when(sender.createMimeMessage())
        .thenAnswer(invocation ->
                new MimeMessage(
                    Session.getInstance(new Properties())));
```

Why use `thenAnswer` to create a new message? Each time the service calls `createMimeMessage()`, it receives a fresh object. If the same `MimeMessage` instance were reused across multiple calls in a test, earlier content/headers could pollute later results and cause false positives or false negatives.

### 5.3. Why is `mock(MimeMessage.class)` not the default choice?

An example unsuitable when the goal is inspecting MIME:

```java
when(sender.createMimeMessage())
        .thenReturn(mock(MimeMessage.class));
```

`MimeMessageHelper` can call `setContent`, `setRecipients`, and other methods on the mock, yet Mockito does not construct multiparts or render content on its own. `verify(sender).send(...)` can still pass even when the actual MIME fails the contract.

Mock `MimeMessage` only if a unit test truly needs to verify narrow outer-layer interactions; when you want to verify what email goes out, a real message is far more valuable.

## 6. Service building HTML, plain text, and PDF attachment

Suppose a use case sends invoices to customers. The contract requires:

- Fixed configured From address.
- One recipient in To.
- Subject containing the invoice number.
- Both `text/plain` and `text/html`.
- UTF-8 charset to display Vietnamese characters properly.
- PDF attachment with the right filename and Content-Type.

### 6.1. Illustrative production code

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class InvoiceMailService {

    private final JavaMailSender sender;
    private final String fromAddress;

    public InvoiceMailService(
            JavaMailSender sender,
            String fromAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
    }

    public void sendInvoice(
            String recipient,
            String invoiceNo,
            byte[] pdfBytes) {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient is required");
        }

        if (invoiceNo == null || invoiceNo.isBlank()) {
            throw new IllegalArgumentException(
                    "Invoice number is required");
        }

        if (pdfBytes == null || pdfBytes.length == 0) {
            throw new IllegalArgumentException(
                    "PDF content is required");
        }

        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper =
                    new MimeMessageHelper(message, true, "UTF-8");

            helper.setFrom(fromAddress);
            helper.setTo(recipient);
            helper.setSubject("Hóa đơn " + invoiceNo);

            String plainText =
                    "Hóa đơn " + invoiceNo + " đã được phát hành.";

            String html = "<html><body>"
                    + "<p>Hóa đơn <strong>"
                    + escapeHtml(invoiceNo)
                    + "</strong> đã được phát hành.</p>"
                    + "</body></html>";

            helper.setText(plainText, html);
            helper.addAttachment(
                    "invoice-" + invoiceNo + ".pdf",
                    new ByteArrayResource(pdfBytes),
                    "application/pdf");

            sender.send(message);

        } catch (MessagingException ex) {
            throw new IllegalStateException(
                    "Unable to prepare invoice email", ex);
        }
    }

    private static String escapeHtml(String value) {
        return value.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }
}
```

This is a standalone example of the mail-sending layer, not a template for an entire business workflow. In production, invoice numbers/filenames must be policy-validated, HTML should be rendered by an auto-escaping template engine, large files need proper storage/stream contracts, and sending typically needs a separate outbox/retry mechanism.

What is worth testing: **the real `MimeMessage` content** produced by the service, not the internal state of `MimeMessageHelper`.

### 6.2. Test capturing a real MimeMessage

```java
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.javamail.JavaMailSender;

import java.nio.charset.StandardCharsets;
import java.util.Properties;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class InvoiceMailServiceTest {

    @Mock
    JavaMailSender sender;

    InvoiceMailService service;

    @BeforeEach
    void setUp() {
        service = new InvoiceMailService(
                sender, "billing@example.com");

        when(sender.createMimeMessage())
                .thenAnswer(invocation ->
                        new MimeMessage(
                            Session.getInstance(new Properties())));
    }

    @Test
    void sendsInvoiceWithExpectedHeaders() throws Exception {
        byte[] pdf = "%PDF-1.4\nsample".getBytes(
                StandardCharsets.US_ASCII);

        service.sendInvoice(
                "minh@example.net",
                "HD-1002",
                pdf);

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender, times(1)).send(captor.capture());

        MimeMessage actual = captor.getValue();
        actual.saveChanges();

        InternetAddress from =
                (InternetAddress) actual.getFrom()[0];
        InternetAddress to =
                (InternetAddress) actual
                        .getRecipients(Message.RecipientType.TO)[0];

        assertThat(from.getAddress())
                .isEqualTo("billing@example.com");
        assertThat(to.getAddress())
                .isEqualTo("minh@example.net");
        assertThat(actual.getSubject())
                .isEqualTo("Hóa đơn HD-1002");
        assertThat(actual.isMimeType("multipart/*"))
                .isTrue();
    }
}
```

`saveChanges()` finalizes MIME headers/metadata on the test object so reading them is consistent. It **does not send over the network**. In tests, avoid asserting exact values for `Message-ID`, MIME boundaries, or sent dates when JavaMail generates them automatically.

### 6.3. Verify charset by reading content, not checking raw headers

For Vietnamese text, the primary goal is that when the message is decoded according to its charset, the content stays intact. For example, the service sets subject `"Hóa đơn HD-1002"` and the test reads `actual.getSubject()`; Jakarta Mail returns the decoded value.

Do not assert that the raw subject equals a specific encoded-word string, since header wrapping/folding can vary across library versions/implementations while remaining MIME-compliant.

For the body, read `Part.getContent()` on the real message to confirm Vietnamese diacritics and special characters remain accurate.

## 7. Read multipart by MIME structure, not fixed positions

A message with plain text, HTML, and a PDF typically has a nested structure, such as:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related (structure may vary by mode)
    │   └── multipart/alternative
    │       ├── text/plain
    │       └── text/html
    └── application/pdf attachment
```

Do not assume:

- `getBodyPart(0)` is always plain text.
- `getBodyPart(1)` is always HTML.
- The PDF is always the last element.
- Every `MimeMessageHelper` mode produces the identical MIME tree.

`MimeMessageHelper` supports multiple multipart modes; the mail library may arrange root mixed, related, and alternative containers as needed. **Tests should locate parts by Content-Type/disposition**, rather than hardcoding positions.

### 7.1. Helper to find text/plain and text/html

Example test utility:

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

final class MimeTestSupport {

    private MimeTestSupport() {}

    static String findBodyText(Part part, String mimeType)
            throws Exception {

        boolean isAttachment =
                Part.ATTACHMENT.equalsIgnoreCase(
                        part.getDisposition())
                || part.getFileName() != null;

        if (!isAttachment && part.isMimeType(mimeType)) {
            Object content = part.getContent();

            if (content instanceof String text) {
                return text;
            }
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                String found = findBodyText(
                        multipart.getBodyPart(i), mimeType);

                if (found != null) {
                    return found;
                }
            }
        }

        return null;
    }
}
```

This helper demonstrates traversing the MIME tree. In advanced tests you may need to distinguish inline resources, `multipart/alternative` preference, and `text/plain` attachments. For the contract in this example, finding plain/HTML bodies with no filename or attachment disposition is sufficient.

### 7.2. Assertions for plain text and HTML

Add to the test that captured `actual`:

```java
String plain = MimeTestSupport.findBodyText(
        actual, "text/plain");
String html = MimeTestSupport.findBodyText(
        actual, "text/html");

assertThat(plain)
        .contains("Hóa đơn HD-1002")
        .contains("đã được phát hành");

assertThat(html)
        .contains("<strong>HD-1002</strong>")
        .contains("đã được phát hành");
```

This way the test checks **both real content versions** instead of only `verify(sender).send(...)`.

### 7.3. HTML escaping is a separate contract

When the HTML body includes untrusted data, verify that such data cannot be injected as arbitrary markup. Example:

```java
service.sendInvoice(
        "minh@example.net",
        "HD<&1002",
        pdf);

MimeMessage actual = captureSentMimeMessage(sender);

String html = MimeTestSupport.findBodyText(
        actual, "text/html");

assertThat(html)
        .contains("HD&lt;&amp;1002")
        .doesNotContain("<strong>HD<&1002</strong>");
```

`captureSentMimeMessage` in the example is a test helper you can write using `ArgumentCaptor<MimeMessage>` as shown earlier. If data is rendered via Thymeleaf, test rendering at the template layer or through a real adapter depending on architecture.

### 7.4. Avoid comparing raw MIME byte-for-byte

A message may be base64-encoded, quoted-printable-encoded, or have random MIME boundaries. Two messages can differ in bytes while behaving identically from the recipient's perspective.

Brittle assertions:

- Comparing the entire `message.writeTo(outputStream)` output against a fixed text file.
- Asserting exact boundary strings.
- Asserting header ordering outside the contract.
- Asserting random `Message-ID` values.

Only use byte-for-byte checks when **wire representation** itself is a special requirement and tests are carefully controlled; most business email unit tests do not need to lock down bytes to that degree.

## 8. Test attachments: filename, MIME type, and byte content

For invoices, checking that `addAttachment` was called is not enough. You must confirm the final message contains the right attachment.

### 8.1. Find attachment by filename

```java
import jakarta.mail.Multipart;
import jakarta.mail.Part;

final class AttachmentTestSupport {

    private AttachmentTestSupport() {}

    static Part findAttachment(Part part, String expectedName)
            throws Exception {

        if (expectedName.equals(part.getFileName())) {
            return part;
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                Part found = findAttachment(
                        multipart.getBodyPart(i),
                        expectedName);

                if (found != null) {
                    return found;
                }
            }
        }

        return null;
    }
}
```

### 8.2. Assert actual content

```java
Part attachment = AttachmentTestSupport.findAttachment(
        actual, "invoice-HD-1002.pdf");

assertThat(attachment).isNotNull();
assertThat(attachment.isMimeType("application/pdf"))
        .isTrue();

byte[] actualBytes;
try (InputStream in = attachment.getInputStream()) {
    actualBytes = in.readAllBytes();
}

assertThat(actualBytes).containsExactly(pdf);
```

You must import `java.io.InputStream`. With `MimeMessageHelper`, attachments may be encoded with MIME transfer encoding; `getInputStream()` returns the decoded content to compare against the input bytes.

### 8.3. PDF content in unit tests

Using a few dummy bytes is enough to test that the adapter **attaches the right bytes**. It does not prove the file is a structurally valid PDF or readable by an application; real PDF validation belongs to a separate test scope.

### 8.4. Large attachments and InputStreamSource

`ByteArrayResource` fits small examples; large production files may be supplied via storage references/streams. With `MimeMessageHelper.addAttachment`, note that the stream source must satisfy Jakarta Mail's reading contract; some sources may be read multiple times while building/serializing the message.

Unit tests should clarify:

- Who owns the stream?
- Can data be opened/read repeatedly?
- Are resources closed after use?
- Does the test verify content/filename rather than merely the presence of a resource object?

Never create an already-consumed `InputStream` and pass it into the send pipeline without a mechanism to open a fresh stream when the API requires one.

## 9. Inline images differ from attachments

HTML emails can reference inline images via Content-ID (CID):

```html
<img src="cid:company-logo" alt="Logo">
```

Services typically use:

```java
helper.setText(html, true);
helper.addInline(
        "company-logo",
        new ByteArrayResource(logoPng),
        "image/png");
```

For inline resources, the contract may specify:

- HTML contains `cid:company-logo`.
- A MIME part has the matching `Content-ID`, commonly represented as `<company-logo>`.
- Content-Type `image/png`.
- Inline-appropriate disposition/filename.
- Correct binary content.

Note on `MimeMessageHelper`: **calling `setText(...)` before `addInline(...)`** is the recommended order so mail readers can resolve the CID part properly. MIME unit tests can verify structure, yet **cannot prove every mail client renders it identically**.

Do not confuse inline images with attachments that recipients download. The two MIME part types carry different semantics even though both contain binary data.

## 10. Special case: send(MimeMessagePreparator)

Many services do not call `createMimeMessage()` directly. Instead, they pass a callback:

```java
public final class PreparedWelcomeMailService {

    private final JavaMailSender sender;
    private final String fromAddress;

    public PreparedWelcomeMailService(
            JavaMailSender sender,
            String fromAddress) {
        this.sender = sender;
        this.fromAddress = fromAddress;
    }

    public void sendWelcome(String recipient, String name) {
        sender.send((MimeMessagePreparator) mime -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, false, "UTF-8");

            helper.setFrom(fromAddress);
            helper.setTo(recipient);
            helper.setSubject("Welcome " + name);
            helper.setText("Hello " + name + "!");
        });
    }
}
```

`MimeMessagePreparator` lives in the `org.springframework.mail.javamail` package; the cast in the example selects the overload taking a preparator explicitly.

### 10.1. Why can a default mock cause a false positive?

A Mockito mock of `JavaMailSender` is a dummy object. The call:

```java
sender.send((MimeMessagePreparator) mime -> {
    // Message-building code goes here.
});
```

only hits the mocked `send` method. Without additional stubbing, Mockito **does not call `prepare(mime)`**, because callbacks are invoked only by a real `JavaMailSender` implementation during sending.

The test:

```java
service.sendWelcome("lan@example.net", "Lan");
verify(sender).send(any(MimeMessagePreparator.class));
```

only tells you a callback was **passed in**; it does not tell you the callback succeeded or prepared the right message.

### 10.2. Approach 1: capture the preparator and run it on a real MimeMessage

```java
@Test
void preparatorProducesCorrectWelcomeMime() throws Exception {
    JavaMailSender sender = mock(JavaMailSender.class);

    PreparedWelcomeMailService service =
            new PreparedWelcomeMailService(
                    sender, "hello@example.com");

    service.sendWelcome("lan@example.net", "Lan");

    ArgumentCaptor<MimeMessagePreparator> captor =
            ArgumentCaptor.forClass(
                    MimeMessagePreparator.class);

    verify(sender).send(captor.capture());

    MimeMessage message = new MimeMessage(
            Session.getInstance(new Properties()));

    // Important: the unit test explicitly invokes the callback.
    captor.getValue().prepare(message);
    message.saveChanges();

    assertThat(message.getSubject())
            .isEqualTo("Welcome Lan");

    InternetAddress to = (InternetAddress) message
            .getRecipients(Message.RecipientType.TO)[0];
    assertThat(to.getAddress())
            .isEqualTo("lan@example.net");

    String plain = MimeTestSupport.findBodyText(
            message, "text/plain");
    assertThat(plain).contains("Hello Lan");
}
```

You must import `MimeMessagePreparator`, `Session`, `Message`, `InternetAddress`, `MimeMessage`, `Properties`, and the corresponding Mockito/AssertJ APIs.

This is the clearest approach when you want to verify both:

1. The service submitted a preparator.
2. The preparator actually built a message with the right content.

### 10.3. Approach 2: doAnswer runs the callback when send is invoked

```java
@Test
void executesPreparatorThroughMockSender() throws Exception {
    JavaMailSender sender = mock(JavaMailSender.class);
    AtomicReference<MimeMessage> built = new AtomicReference<>();

    doAnswer(invocation -> {
        MimeMessagePreparator preparator =
                invocation.getArgument(
                        0, MimeMessagePreparator.class);

        MimeMessage mime = new MimeMessage(
                Session.getInstance(new Properties()));

        preparator.prepare(mime);
        mime.saveChanges();
        built.set(mime);
        return null; // send(...) is void
    }).when(sender).send(any(MimeMessagePreparator.class));

    PreparedWelcomeMailService service =
            new PreparedWelcomeMailService(
                    sender, "hello@example.com");

    service.sendWelcome("lan@example.net", "Lan");

    verify(sender).send(any(MimeMessagePreparator.class));
    assertThat(built.get()).isNotNull();
    assertThat(built.get().getSubject())
            .isEqualTo("Welcome Lan");
}
```

You must import `java.util.concurrent.atomic.AtomicReference`. This causes the mock sender to execute the callback immediately when the service calls send. It is useful when simulating callback interaction closely matching the real implementation.

**Never treat this `doAnswer` as an SMTP server model**: it still opens no network, simulates no TLS/AUTH, and does not tell you whether the provider accepts the message.

### 10.4. Why should you not mock the service's own preparator?

If the service is responsible for creating the preparator from business data, testing with a different fake preparator skips the code under test. The right approach is capturing **the preparator the service actually passed** and checking what it builds.

### 10.5. Errors inside a preparator and mock behavior

The real `JavaMailSender.send(MimeMessagePreparator)` implementation may translate message-preparation errors into `MailPreparationException` per Spring Mail's mechanism. An unstubbed Mockito mock does not run the callback, so it will not throw preparation exceptions either.

To test the failure path when the callback throws:

- Capture and run `prepare` on a real `MimeMessage` and observe the exception at `prepare`.
- Or use `doAnswer` simulating the exception-translation rule the application depends on, if that is part of the contract.
- To verify how Spring's implementation wraps exceptions, move to an appropriate integration/adapter test.

Never gain false confidence just because a mock threw no exception when the callback was never even executed.

## 11. Mock array/batch send overloads

`JavaMailSender` can accept multiple `SimpleMailMessage` or `MimeMessage` instances in one batch call.

### 11.1. Example service sending multiple SimpleMailMessages

```java
public void sendBatch(List<String> recipients) {
    SimpleMailMessage[] messages = recipients.stream()
            .map(recipient -> {
                SimpleMailMessage mail = new SimpleMailMessage();
                mail.setFrom("notifications@example.com");
                mail.setTo(recipient);
                mail.setSubject("Notification");
                mail.setText("Content");
                return mail;
            })
            .toArray(SimpleMailMessage[]::new);

    sender.send(messages);
}
```

To test the batch contract, you can use:

```java
ArgumentCaptor<SimpleMailMessage[]> captor =
        ArgumentCaptor.forClass(SimpleMailMessage[].class);

service.sendBatch(List.of(
        "a@example.net",
        "b@example.net"));

verify(sender).send(captor.capture());

SimpleMailMessage[] actual = captor.getValue();

assertThat(actual).hasSize(2);
assertThat(actual[0].getTo())
        .containsExactly("a@example.net");
assertThat(actual[1].getTo())
        .containsExactly("b@example.net");
```

With Mockito versions that handle varargs specifically, array matchers/captors must match the exact `SimpleMailMessage[]` type. If the test reports an overload mismatch, check the method signature selected by Java and your Mockito version.

### 11.2. Do not confuse a batch request with per-message delivery

A single `send(messages)` call can result in partial failure in a real implementation. Mocks do not simulate one element succeeding while another fails by default.

If the application must track per-recipient status, design the contract/adapter to expose corresponding results and add integration tests. Capturing an array alone does not prove partial-failure retries are safe.

### 11.3. Why avoid overly generic varargs stubbing?

A stub such as `doNothing().when(sender).send(any())` can be ambiguous across overloads or fail compilation on widely overloaded APIs. Use typed matchers or capture the exact array type.

## 12. Test the right exception types from JavaMailSender

A good unit test covers more than the happy path. When the sender throws `MailException`, the mail service must follow the right policy:

- Propagate technical errors up to the adapter/application boundary?
- Translate into a neutral application exception?
- Record retry/outbox state?
- Avoid marking a notification as submitted without evidence?

Never write code that swallows errors:

```java
try {
    sender.send(message);
} catch (MailException ex) {
    log.warn("Could not send mail");
    // Caller not notified / retry not persisted.
}
```

If callers assume sending succeeded and mark a business operation complete, a critical notification can be silently lost.

### 12.1. Example error-translating service

Suppose the application defines a neutral exception:

```java
public class NotificationSubmissionException
        extends RuntimeException {

    public NotificationSubmissionException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Adapter/service:

```java
public void submit(OutgoingEmail email) {
    MimeMessage message = buildMimeMessage(email);

    try {
        sender.send(message);
    } catch (MailException ex) {
        throw new NotificationSubmissionException(
                "Mail submission failed", ex);
    }
}
```

`OutgoingEmail`, `buildMimeMessage`, and the exception are application-owned abstractions in this example, not built-in Spring classes.

### 12.2. Mockito doThrow for void send

```java
doThrow(new MailSendException("SMTP server unavailable"))
        .when(sender)
        .send(any(MimeMessage.class));
```

After calling the service, you can assert:

```java
assertThatThrownBy(() -> service.submit(email))
        .isInstanceOf(
                NotificationSubmissionException.class)
        .hasCauseInstanceOf(MailSendException.class);

verify(sender, times(1))
        .send(any(MimeMessage.class));
```

This test checks the error-translation layer, yet **cannot classify all SMTP 4xx/5xx codes**. If retry policy depends on SMTP stage/code, test the classifier separately with matching exceptions/metadata or integration tests against a test transport.

### 12.3. Authentication, preparation, and send errors differ

| Error type | Common source | Unit test check |
|---|---|---|
| `MailAuthenticationException` | SMTP AUTH | Never mark succeeded; classify accurately per policy |
| `MailSendException` | Transport send failure | Translate error/record retry per application contract |
| `MailParseException` | Message data/format | Never blindly retry SMTP |
| `MailPreparationException` | Message preparation, especially preparators | Never assume callbacks ran inside a mock |
| `MessagingException` | Jakarta Mail/MIME operations | Verify preparation code handles it appropriately |

Never treat every `MailException` as transient and retryable. TLS certificate errors, bad credentials, invalid MIME data, or permanent recipient rejections require different handling.

### 12.4. Pitfall when constructing fake exceptions

If a test creates `MailSendException("SMTP unavailable")` with no nested cause, the test only verifies how the application reacts to the **outer exception type**. It is insufficient to prove a classifier recognizes `ConnectException`, `SocketTimeoutException`, SMTP reply codes, and unknown submission outcomes.

For classifiers, write dedicated test cases with structured cause chains and test the classification logic directly; never claim tests cover network semantics when they do not.

## 13. Test "do not call sender" when business rules reject

A use case may forbid sending when:

- The recipient has not verified their address when that notification type requires it.
- A marketing notification lacks consent.
- The customer has unsubscribed.
- The event was already processed and a notification intent already exists.
- An OTP email has expired.
- A required attachment file is missing.

Test at the right layer:

```java
@Test
void doesNotSubmitWhenRecipientIsSuppressed() {
    when(suppressionPolicy.isSuppressed(
            "lan@example.net"))
            .thenReturn(true);

    notificationUseCase.execute(
            notificationFor("lan@example.net"));

    verifyNoInteractions(mailDeliveryPort);
}
```

Here `suppressionPolicy`, `mailDeliveryPort`, and `notificationUseCase` are illustrative application-level collaborators. If the use case only writes an outbox record, the right assertion is **no intent created** rather than `verifyNoInteractions(javaMailSender)`, since `JavaMailSender` is not called in that use case anyway.

### 13.1. "No interactions" only makes sense at the right boundary

Avoid using `verifyNoInteractions(sender)` as a requirement for every error test. A service might build a message and call `createMimeMessage()` before noticing bad input; tests must decide whether that is a validation-order bug or an irrelevant internal detail.

When validation must precede I/O/submission, a "not sent" test can use:

```java
verify(sender, never())
        .send(any(MimeMessage.class));
```

This verifies "not submitted" without requiring "no object created" when that is not part of the contract.

### 13.2. Preventing duplicate sends is an outbox contract, not an SMTP mock check

Suppose a domain event is processed twice:

```java
handler.handle(event);
handler.handle(event);
```

If the handler only writes to an outbox, tests should assert **the number of outbox rows or effective inserts** enforced by a unique key. You cannot prove distributed deduplication via `verify(sender, times(1))` when sending runs in a background worker after the transaction.

## 14. Test multiple recipients, Cc, and Bcc

If the application contract supports multiple recipients, tests must inspect recipient types.

```java
InternetAddress[] to = (InternetAddress[])
        Arrays.copyOf(
                actual.getRecipients(Message.RecipientType.TO),
                actual.getRecipients(
                        Message.RecipientType.TO).length,
                InternetAddress[].class);
```

The snippet above illustrates copying the array; more simply, you can assert directly on each `Address`:

```java
Address[] toRecipients =
        actual.getRecipients(Message.RecipientType.TO);
Address[] ccRecipients =
        actual.getRecipients(Message.RecipientType.CC);
Address[] bccRecipients =
        actual.getRecipients(Message.RecipientType.BCC);

assertThat(toRecipients).hasSize(1);
assertThat(((InternetAddress) toRecipients[0]).getAddress())
        .isEqualTo("buyer@example.net");
assertThat(ccRecipients).isNullOrEmpty();
assertThat(bccRecipients).isNullOrEmpty();
```

For individualized customer emails, never accidentally expose private recipient lists in `To` or `Cc`. When Bcc is used, tests must distinguish **envelope recipients** from headers: Bcc may exist on the prepared message object, yet must not be exposed to final recipients as a public header when handled by the transport.

Unit tests inspect the object entering the sender; hiding/stripping Bcc in SMTP transport must be tested at the appropriate layer.

## 15. Subject, Reply-To, and Unicode

### 15.1. Subject with Vietnamese diacritics

```java
helper.setSubject("Xác nhận đơn hàng đã thanh toán");
```

Test:

```java
assertThat(actual.getSubject())
        .isEqualTo("Xác nhận đơn hàng đã thanh toán");
```

Do not assert raw encoded-words in `Subject`. Jakarta Mail may MIME-encode the header for transport and decode it when read back.

### 15.2. From display name

```java
helper.setFrom(
        new InternetAddress(
                "support@example.com",
                "Bộ phận hỗ trợ",
                "UTF-8"));
```

Test:

```java
InternetAddress from =
        (InternetAddress) actual.getFrom()[0];

assertThat(from.getAddress())
        .isEqualTo("support@example.com");
assertThat(from.getPersonal())
        .isEqualTo("Bộ phận hỗ trợ");
```

Check the logical decoded value rather than locking down header folding.

### 15.3. Reply-To

If the business contract requires replies to go to support, verify `Reply-To` separately:

```java
helper.setReplyTo("helpdesk@example.com");
```

```java
InternetAddress replyTo =
        (InternetAddress) actual.getReplyTo()[0];

assertThat(replyTo.getAddress())
        .isEqualTo("helpdesk@example.com");
```

Do not confuse `Reply-To` with the envelope `MAIL FROM` or `Return-Path`; those are distinct concepts in SMTP/email.

### 15.4. Do not infer IP reputation from header unit tests

Correct From/Reply-To/Subject headers do not prove SPF/DKIM/DMARC or PTR records are valid. Those configurations belong to domain DNS and the SMTP provider/MTA, and cannot be proven by mocking `JavaMailSender`.

## 16. Dates, IDs, and dynamic content: keep tests deterministic

Emails often include:

- Invoice issue date.
- Expiring verification links.
- Order numbers.
- Recipient names.
- Locale/time zone.
- Trace or notification IDs.

If the service calls `Instant.now()` directly, assertions can depend on execution timing. It is better to inject `Clock`:

```java
public final class PasswordResetMailContent {

    private final Clock clock;

    public PasswordResetMailContent(Clock clock) {
        this.clock = clock;
    }

    public String buildExpiryNotice(Duration validity) {
        Instant expiresAt = clock.instant().plus(validity);
        return "Link expires at " + expiresAt;
    }
}
```

In tests:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-12T08:00:00Z"),
        ZoneOffset.UTC);

PasswordResetMailContent content =
        new PasswordResetMailContent(fixedClock);

assertThat(content.buildExpiryNotice(Duration.ofMinutes(15)))
        .contains("2026-11-12T08:15:00Z");
```

Facts such as tokens, UUIDs, and URLs should also be supplied through controlled dependencies/fixtures rather than generated randomly and asserted against fixed strings.

### 16.1. Links need more than just contains checks

A verification link could have the right host yet the wrong scheme or an improperly escaped token. For critical links, test the content factory/template separately:

- Scheme must be HTTPS per policy.
- Host/path belong to the allowlist.
- Token is contextually URL-encoded.
- Query parameters are accurate.
- Secrets are never logged.
- Expiration does not exceed business rules.

Mockito does not replace link and escaping validation; it only helps capture the message the service built.

## 17. Unit tests with @MockitoBean or @MockBean when Spring context is truly needed

Most mail service tests do not need a Spring context. However, if you need to test wiring or a Spring-managed controller/use case:

- In Spring Framework versions supporting bean-override testing, use `@MockitoBean` to replace `JavaMailSender` in the test `ApplicationContext`.
- Older Spring Boot projects use `@MockBean`; that annotation has been superseded in newer versions, so pick the annotation matching your actual version.
- When testing pure constructor-injected service logic, `@Mock` and `MockitoExtension` remain leaner and faster.

Example layout for a Spring application with the matching bean-override API:

```java
@SpringBootTest
class OrderWorkflowIntegrationTest {

    @MockitoBean
    JavaMailSender javaMailSender;

    @Autowired
    OrderWorkflowService workflowService;

    @Test
    void requestsEmailAfterWorkflow() {
        // Configure required dependencies.
        // Invoke workflowService.
        // Verify the exact contract at this boundary.
    }
}
```

This snippet is a structural sketch, **not an isolated unit test**; context startup, transaction listeners, or async boundaries can affect when verification runs. Do not convert every unit test into `@SpringBootTest` just to mock the sender.

### 17.1. Constructor injection vs field injection

When a service takes dependencies via constructor, tests can easily instantiate and configure it explicitly. Field injection via `@Autowired` in the class under test makes unit testing heavier or forces reflection to populate fields.

### 17.2. @InjectMocks does not solve everything

Mockito `@InjectMocks` wires mocks into an instance in many cases, yet cannot substitute for explicit constructor arguments, dynamic configuration, or From values. If a service requires `Clock`, properties, and template renderers, constructing it explicitly in `@BeforeEach` is usually clearer and more reliable.

## 18. When services send asynchronously or via an outbox

Many architectures do not call `JavaMailSender.send` directly inside a use case. For instance:

```text
OrderConfirmed use case
        |
        v
NotificationOutboxRepository.insertIfAbsent(...)
        |
        v
Database commit
        |
        v
Scheduled/queue worker
        |
        v
SpringMailDeliveryAdapter
        |
        v
JavaMailSender.send(...)
```

### 18.1. Unit test contract for the use case

Verify:

- Event maps to the right notification intent.
- Idempotency key is right.
- Payload to send is persisted.
- No duplicate notifications are created.
- Transactions/policies coordinate appropriately.

Do not require `verify(javaMailSender).send(...)` in a use-case unit test when the use case does not send directly.

### 18.2. Unit test contract for the worker

Verify:

- Only validly claimed notifications are processed.
- Issues **one attempt** through the mail delivery port.
- Transitions state to `SUBMITTED` when transport reports success.
- Stores `RETRY_WAIT` with backoff on transient errors.
- Halts or reconciles when submission outcome is unknown.
- Does not create a new outbox row on every retry.

Mock the outbound port or sender at the boundary under test; do not mock a dependency far removed from the layer under test.

### 18.3. Unit test contract for SpringMailDeliveryAdapter

This is the right place to mock `JavaMailSender`, capture `MimeMessage`, and verify From/To/Subject/MIME.

An adapter should not invent unbounded retries inside `send`; the application/outbox worker manages attempts, states, and idempotency.

### 18.4. Async tests need explicit synchronization points

A test calling an `@Async` service and immediately running `verify(sender)` can fail intermittently because the send call has not executed yet. Design proper synchronization/awaiting in integration tests, or extract synchronous logic into a separate component for unit testing.

Never rely on `Thread.sleep(500)` as proof an event was processed. A fixed sleep does not prove system stability.

## 19. Distinguish verify(send) from real SMTP verification

Suppose a test passes:

```java
verify(sender, times(1)).send(any(MimeMessage.class));
```

What you can conclude: **the code under test called the mock sender once with a `MimeMessage` matching that overload**.

What you cannot conclude:

- The SMTP host DNS resolves.
- The TCP port is reachable.
- STARTTLS succeeds.
- The trust store and certificate chain are valid.
- SMTP AUTH succeeds.
- The MX accepts the recipient.
- SPF/DKIM/DMARC pass.
- Attachments render identically across all clients.
- The provider does not bounce.
- The email reached the Inbox.
- Retrying after a process crash will not create duplicates.

Those claims require different checks. Never report "Email sent successfully" based on Mockito verify; state accurately "mail submission request was issued to mocked JavaMailSender."

## 20. Design tests using a contract matrix

A helpful scenario checklist for an invoice-sending mail service:

| Case | Input facts | Key assertions |
|---|---|---|
| Happy path | Valid recipient, invoice no, PDF bytes | `send(MimeMessage)` once; From/To/Subject correct |
| Plain + HTML | Body contains Vietnamese | Both `text/plain` and `text/html` found, decoded accurately |
| Attachment | PDF bytes and filename | `application/pdf` MIME part has exact bytes |
| Invalid recipient | Blank/null | Throws validation exception; never submits |
| Missing attachment | Missing required file | Never sends email missing invoice |
| HTML special chars | Code/name with `&`, `<`, `>` | HTML is contextually escaped |
| Mail transport failure | Sender throws `MailSendException` | Error translated/propagated properly, never marked submitted |
| Preparator callback | Service uses `MimeMessagePreparator` | Capture and run callback on a real message |
| Dynamic date | Fixed `Clock` | Expiry/date accurate, independent of wall-clock time |
| Batch | Two recipients | Right array overload and each element's data |
| Outbox duplicate | Same event ID processed again | No new notification intent created |
| Worker retry | Transient error | Same notification ID, next attempt per policy |
| Uncertain submission | Timeout after DATA | Never assume the email was definitely not sent |

One unit test class does not have to contain every case; split by responsibility. In particular, outbox duplicates, worker claiming, and real SMTP results belong to different layers.

## 21. Common pitfalls when mocking JavaMailSender

### 21.1. Only verifying "any message"

`verify(sender).send(any(MimeMessage.class))` checks no data. Use `ArgumentCaptor` and inspect real MIME when content is part of the contract.

### 21.2. Mocking MimeMessage instead of using a real object

Calling `MimeMessageHelper` on a mock produces no real content. Use `MimeMessage(Session.getInstance(new Properties()))` in tests.

### 21.3. Forgetting to stub createMimeMessage()

Mockito returns `null` by default for factory methods if unstubbed. The service may throw `NullPointerException` before sending. Use `thenAnswer` returning a fresh real MIME object per call.

### 21.4. Using when/thenReturn on void send

`send(...)` returns `void`. Use `doThrow`, `doAnswer`, or simply `verify`.

### 21.5. Ignoring overloads

Service calls `send(SimpleMailMessage)` while test verifies `send(MimeMessage)`. Matchers must match the exact parameter type.

### 21.6. Forgetting to execute MimeMessagePreparator

Mock `send(preparator)` does not invoke the callback. Capture the callback and call `prepare(realMime)` or use `doAnswer`.

### 21.7. Asserting MIME parts at fixed positions

Multipart trees can be nested. Traverse by MIME type/filename/disposition.

### 21.8. Comparing raw MIME boundaries

Boundaries, transfer encodings, and header folding can change. Test logical content rather than locking down raw message bytes.

### 21.9. Skipping charsets and Vietnamese text checks

ASCII-only tests miss encoding bugs. Add Unicode fixtures and assert decoded content.

### 21.10. Skipping attachment filename/bytes checks

An attachment added with the wrong type or empty bytes can still pass a `send(any(...))` test.

### 21.11. Mixing unit tests with real SMTP

A unit test calling an external server is slow, coupled to network/credentials, and hard to reproduce. Use Mockito at the unit layer and an SMTP catcher at the integration layer.

### 21.12. Catching exceptions and ignoring them

Happy-path tests miss code swallowing `MailException`. Add failure-path tests confirming errors are handled properly.

### 21.13. Tests coupled to wall-clock time

`Instant.now()` and `Thread.sleep` cause flaky tests. Inject `Clock` and test fixed timestamps.

### 21.14. Unnecessary @SpringBootTest

Booting an entire context just to capture subject/recipient is usually overkill. Unit tests with constructor injection suffice.

### 21.15. Assuming verify times(1) proves exactly-once

Mockito only counts invocations within the test process. Distributed deduplication requires outbox/unique constraints and dedicated tests.

### 21.16. Forgetting negative "must not send" tests

Negative tests matter: invalid inputs, suppressed recipients, or expired notifications must not be submitted.

### 21.17. Over-mocking deep dependencies

If a test has to mock `MimeMultipart`, `MimeBodyPart`, `InternetAddress`, and `MimeMessage` all at once, it is likely coupled to too many internals. Real in-memory MIME objects are simpler and more accurate.

### 21.18. Failing to separate preparation errors from transport errors

`MessagingException` while building MIME is not SMTP `MailSendException`. Test appropriate behavior for each group.

### 21.19. Assuming mocks wrap MailPreparationException automatically

Real `JavaMailSenderImpl` has its own wrapping logic. Mockito neither executes preparators nor wraps errors like the real implementation. To verify framework behavior, write an appropriate test.

### 21.20. Over-constraining tests with verifyNoMoreInteractions

`verifyNoMoreInteractions(sender)` can be helpful when strictly preventing extra calls, yet often makes tests brittle if implementation adds a harmless helper interaction like creating an object. Clarify which interactions truly matter before using it.

## 22. A practical workflow for building valuable tests

When adding a new email type, a development workflow can follow:

1. Write out the contract in terms of data: From, To, Subject, plain/HTML, attachments, and non-send criteria.
2. Identify the Spring Mail API used by the service: `SimpleMailMessage`, `MimeMessage`, or `MimeMessagePreparator`.
3. Pick the test boundary: mail adapter, content renderer, application use case, or outbox worker.
4. Mock **JavaMailSender** if the adapter actually depends on it.
5. For MIME, provide a real `MimeMessage` via `createMimeMessage()` or run the preparator explicitly.
6. Capture the message/preparator with the matching overload.
7. Assert logical fields and MIME content; avoid random details.
8. Add negative/failure-path tests.
9. Delegate claims about SMTP/TLS/delivery to integration or operational tests.
10. If notification logic includes retries/idempotency, test them in the right service/repository/worker.

This workflow guides test design rather than serving as a rigid per-test scoring checklist.

## 23. Practice exercises

### Exercise 1 — SimpleMailMessage

Write `WelcomeMailService` taking `JavaMailSender` via constructor. Use `ArgumentCaptor<SimpleMailMessage>` to verify From, To, Subject, and body. Add a blank-recipient test asserting `send` is not called.

### Exercise 2 — Fixing a weak test

Given:

```java
service.sendInvoice(...);
verify(sender).send(any(MimeMessage.class));
```

Explain at least five configuration/content bugs this test fails to catch. Rewrite the test using a real `MimeMessage` and a captor.

### Exercise 3 — Stubbing createMimeMessage

Why is `when(sender.createMimeMessage()).thenReturn(mock(MimeMessage.class))` unsuitable for multipart testing? Replace it with `thenAnswer` creating a real message and explain why a fresh instance per call matters.

### Exercise 4 — MimeMessagePreparator

A service calls `sender.send(mime -> { ... })`. The test only checks `verify(sender).send(any(MimeMessagePreparator.class))`. Use a captor to invoke `prepare` and verify subject, recipients, and body.

### Exercise 5 — doAnswer

Write a `doAnswer` stub for `send(MimeMessagePreparator)` that runs the callback on a real `MimeMessage`, stores it in an `AtomicReference`, and asserts the built content.

### Exercise 6 — Multipart text alternatives

Create a message with plain text and HTML. Write a recursive `Multipart` traversal helper to find `text/plain` and `text/html` without assuming part positions.

### Exercise 7 — Attachment

Attach a PDF using `ByteArrayResource`. In the test, locate the MIME part by filename, assert `application/pdf`, and compare decoded bytes via `getInputStream()`.

### Exercise 8 — UTF-8 and display name

Add a From display name `"Bộ phận chăm sóc khách hàng"` and an accented subject. Assert decoded values without comparing raw header bytes.

### Exercise 9 — HTML injection

An invoice code or customer name contains `<`, `>`, and `&`. Write a test proving HTML is escaped, and contrast it with plain-text bodies that need no HTML escaping.

### Exercise 10 — Exception flow

Mock `JavaMailSender` to throw `MailSendException` from `send(MimeMessage)`. Verify the service translates it to `NotificationSubmissionException`, preserves the original cause, and never marks state as submitted.

### Exercise 11 — Batch overload

A service uses `send(SimpleMailMessage[])`. Capture the array and assert count and recipient ordering per contract. Explain why `any(SimpleMailMessage.class)` does not match the array overload.

### Exercise 12 — Do not send when suppressed

Write a notification use case with `SuppressionPolicy`. Verify users unsubscribed from marketing neither generate a notification intent nor invoke the corresponding mail delivery port.

### Exercise 13 — Idempotency at the right layer

The same `OrderConfirmed(eventId=E-1)` is processed twice, yet the architecture uses a transactional outbox. Show why `verify(javaMailSender, times(1))` is the wrong test and design assertions on the repository/unique key.

### Exercise 14 — Async boundary

An `@Async` listener sends emails. Explain why a test using `Thread.sleep(100)` is flaky and propose splitting out a synchronous component for unit testing or testing async with explicit synchronization.

### Exercise 15 — Contract vs integration

Classify these requirements into unit/integration/operational tests: right subject, valid TLS trust store, SMTP AUTH succeeds, right PDF bytes, DKIM passes, one intent emitted per event, MX accepts mail, user Inbox placement.

### Exercise 16 — Test design review

Review a test class with `@Mock` fields for `MimeMessage`, `MimeMultipart`, `MimeBodyPart`, and `JavaMailSender` that only verifies 20 setter calls. Rewrite it mocking only the sender, using real MIME objects, and asserting meaningful fields.

## 24. Key takeaways and references

To **mock `JavaMailSender` according to the contract under test** in Spring Framework Mail:

1. Define **what behavior the application promises** before deciding which methods to verify.
2. `JavaMailSender` has overloads for `SimpleMailMessage`, `MimeMessage`, `MimeMessagePreparator`, and arrays; matchers/captors must match the exact types.
3. `send(...)` returns `void`; use `doThrow` and `doAnswer` when needed, never `when(...).thenReturn(...)`.
4. **Mock `JavaMailSender`, yet use a real `MimeMessage`** in unit tests inspecting MIME content.
5. Stub `createMimeMessage()` to return a real message; `thenAnswer` supplies a fresh object per call.
6. Use `ArgumentCaptor` to inspect From, To/Cc/Bcc, Subject, `text/plain`, `text/html`, charsets, and attachments.
7. Traverse multiparts by MIME type/filename/disposition; never assume body part positions or compare entire raw MIME bytes.
8. With `send(MimeMessagePreparator)`, **a Mockito mock does not run the callback**: capture it and call `prepare(realMessage)` or use `doAnswer`.
9. Test both **not sending** on invalid input/policy and **error handling** when the sender throws exceptions.
10. Use `Clock`/stable fixtures for dynamic data; verify HTML escaping and URLs contextually.
11. Application use-case unit tests target a mail port or outbox repository; mock `JavaMailSender` only at the layer that calls it directly.
12. `verify(sender).send(...)` **does not** prove SMTP/TLS/AUTH, SPF/DKIM/DMARC, delivery, or Inbox placement.
13. `times(1)` only counts calls within the test; distributed idempotency requires unique keys/outbox tables and dedicated tests.
14. Use an SMTP catcher/integration test for protocol checks, and provider/operational tests for deliverability.

Technical documentation worth referencing:

- **Spring Framework Reference — Email:** sending simple mail, MIME mail, and using `JavaMailSender`.
- **Spring Framework API — `JavaMailSender` / `MailSender`:** `send` overloads, `createMimeMessage`, and exception contracts.
- **Spring Framework API — `MimeMessageHelper`:** plain/HTML alternatives, attachments, inline resources, and multipart modes.
- **Spring Framework API — `MimeMessagePreparator`:** callback-based message preparation and sending.
- **Jakarta Mail API — `MimeMessage`, `Message`, `Multipart`, `Part`, and `InternetAddress`:** inspecting MIME/headers in memory.
- **Mockito Documentation:** `@Mock`, `MockitoExtension`, `ArgumentCaptor`, `doAnswer`, `doThrow`, matchers, and varargs.
- **JUnit Jupiter User Guide:** organizing unit tests, extension lifecycle, and assertion patterns.
- **AssertJ Documentation:** string, array, and exception/cause assertions.
- **Spring Framework Test bean override / MockitoBean:** replacing beans in a test `ApplicationContext` when integration needs arise.
- **Spring Boot Test Reference:** `spring-boot-starter-test` and context mock annotations per project version.
- **GreenMail/Mailpit documentation:** SMTP test servers for integration tests without sending to real mailboxes.

**A trustworthy unit test does not stop at verifying `JavaMailSender.send(...)` was called.** It verifies the exact overload and contracted data; for MIME, it lets Jakarta Mail build a real in-memory object; for preparators, it runs the callback; for failures, it checks the application's response. Only by keeping **mock APIs**, **MIME structure**, and **SMTP transport** clearly separated will your tests stay fast, reliable, and capable of catching bugs recipients would actually see.
