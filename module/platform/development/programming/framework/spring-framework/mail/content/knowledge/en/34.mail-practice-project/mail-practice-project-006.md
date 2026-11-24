# Testing Messages with a Mock JavaMailSender — Spring Framework Mail Practice Project

## 1. Objective of the Practice Project

In a Spring Framework Mail project, email-sending logic usually sits between business workflows and the SMTP system. When a transaction completes, the service must build the right message: recipient address, sender address, subject, body, MIME type, and send eligibility conditions. **Mocking `JavaMailSender`** lets you test these decisions quickly, deterministically, and **without sending emails to the Internet**.

After completing this practice project, you will be able to:

1. Structure a Spring Boot project using `spring-boot-starter-mail`, JUnit 5, and Mockito.
2. Write a service sending `SimpleMailMessage` and a service sending `MimeMessage` with plain text, HTML, and attachments.
3. Replace `JavaMailSender` with a mock in unit tests without needing SMTP credentials.
4. Use `verify`, `times`, `never`, `ArgumentCaptor`, and `verifyNoInteractions` to assert invocations and content.
5. Construct a **real** `MimeMessage` using Jakarta Mail in tests while still mocking the send call, then inspect the MIME structure.
6. Simulate `MailException`, test failure branches, and avoid marking a message as delivered without evidence.
7. Understand when mocks suffice and when a test SMTP server or real provider is needed.

**Target outcome:** a network-independent unit test suite where each assertion proves a specific application behavior without falsely claiming to verify deliverability.

> Scope of proof: `verify(sender).send(message)` proves an invocation on a mock. It does **not** prove the SMTP relay accepted it, the mailbox exists, the email landed in the Inbox, or the recipient read it. This is a practice project on **message composition and orchestration**, not a measurement of Inbox placement rate.

## 2. Project Context

Suppose an e-commerce application needs to send a receipt once an order has been processed. For each request, the service must:

- Construct a message only when the recipient and order ID are valid.
- Consult a business policy on whether transactional emails may be sent to that recipient.
- Send from `billing@example.test` with `Reply-To` set to `support@example.test`.
- Include the order ID in the subject and confirmation text in the body.
- **Never call the sender** when the policy rejects sending.
- **Never swallow errors and report success** if the sender throws an exception.

Another requirement sends an invoice with both plain-text and HTML versions alongside an attachment. For that, we use `MimeMessageHelper`.

### Component Diagram

~~~mermaid
flowchart LR
    A["Business event / API"] --> B["ReceiptMailService"]
    B --> C["RecipientPolicy"]
    B --> D["JavaMailSender"]
    D --> E["SMTP relay"]
    T["JUnit + Mockito"] -. "mock policy" .-> C
    T -. "mock sender" .-> D
~~~

In unit tests, D is replaced by a Mockito mock so **the arrow D → E never actually executes**. That is intentional: the test focuses on service behavior.

## 3. Tools and Versions

The examples use:

| Component | Role |
| --- | --- |
| Java 17 or later | Records, `String.isBlank()`, Java Time |
| Spring Boot compatible with Jakarta Mail | Dependency injection and mail starter |
| Spring Framework Mail | `JavaMailSender`, `SimpleMailMessage`, `MimeMessageHelper` |
| Jakarta Mail | `MimeMessage`, `Session`, `Multipart`, `Part` |
| JUnit Jupiter (JUnit 5) | Authoring test cases |
| Mockito + Mockito JUnit Jupiter | Creating mocks, injecting mocks, verifying/capturing |
| Gradle or Maven | Managing dependencies and running tests |

Examples target Spring Framework 6+ / Spring Boot 3+ with the `jakarta.mail` namespace. If your project still runs on an older generation with `javax.mail`, choose matching dependencies and namespaces across the entire project; **never mix `javax.mail.MimeMessage` with `jakarta.mail.internet.MimeMessage`**.

### Gradle Dependencies

When initializing a project from Spring Initializr, select **Spring Boot**, **Java**, **Spring Boot Starter Mail**, and **Spring Boot Starter Test**. In `build.gradle`, using Spring Boot's selected dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.mockito:mockito-junit-jupiter'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

In several Spring Boot versions, `spring-boot-starter-test` already includes Mockito and JUnit Jupiter; declaring `mockito-junit-jupiter` explicitly makes intent clear. Let dependency management handle compatible versions rather than mixing arbitrary Mockito/Jakarta Mail versions.

### Maven Dependencies

With Maven and a compatible Spring Boot parent/BOM:

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
        <groupId>org.mockito</groupId>
        <artifactId>mockito-junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The XML snippet is the `dependencies` section, not a full `pom.xml`. If your project does not use a Spring Boot parent/BOM, manage compatible versions manually.

### Do Not Configure Real SMTP for Unit Tests

Mockito tests create a mock `JavaMailSender`, so there is no need for:

~~~text
spring.mail.host
spring.mail.port
spring.mail.username
spring.mail.password
~~~

Never use real Gmail/corporate SMTP accounts, passwords, or real recipients to run these tests. Doing so is unnecessary, makes unit tests slow and network-dependent, and risks sending unintended emails.

## 4. Reference Project Structure

~~~text
src/
  main/
    java/com/example/mail/
      RecipientPolicy.java
      ReceiptMailService.java
      HtmlReceiptMailService.java
  test/
    java/com/example/mail/
      ReceiptMailServiceTest.java
      ReceiptMailServiceFailureTest.java
      HtmlReceiptMailServiceTest.java
      MailTestSupport.java
~~~

These files form a **sample structure for hands-on practice**. You do not need a real controller or a full Spring context to unit-test these services: Mockito can instantiate objects via constructors.

## 5. Creating the RecipientPolicy Interface

First, decouple the decision of "whether transactional mail may be sent" from transport.

**`src/main/java/com/example/mail/RecipientPolicy.java`**

~~~java
package com.example.mail;

public interface RecipientPolicy {
    boolean canReceiveTransactionalMail(String recipient);
}
~~~

This interface provides a seam to mock in tests. In a real application, the implementation may inspect account status, per-category suppressions, permissions, and business rules. **Never assume a marketing unsubscribe automatically blocks every mandatory transactional email**; each category needs its own rules.

### Why Keep Policy Out of JavaMailSender?

`JavaMailSender` does not know whether an order is valid, which tenant a recipient belongs to, or which mail categories a user opted out of. Those decisions belong in the business layer where they can be tested independently. Mocking the sender does not replace permission or consent checks.

## 6. Writing the Service Using SimpleMailMessage

**`src/main/java/com/example/mail/ReceiptMailService.java`**

~~~java
package com.example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public final class ReceiptMailService {

    private final JavaMailSender mailSender;
    private final RecipientPolicy recipientPolicy;

    public ReceiptMailService(
            JavaMailSender mailSender,
            RecipientPolicy recipientPolicy) {
        this.mailSender = mailSender;
        this.recipientPolicy = recipientPolicy;
    }

    public void sendReceipt(String recipient, String orderId) {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient must not be blank");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "Order ID must not be blank");
        }

        if (!recipientPolicy.canReceiveTransactionalMail(recipient)) {
            return;
        }

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("billing@example.test");
        message.setReplyTo("support@example.test");
        message.setTo(recipient);
        message.setSubject("Receipt for order " + orderId);
        message.setText(
                "Your order " + orderId + " has been recorded.");

        mailSender.send(message);
    }
}
~~~

### Flow Explanation

1. Constructor injection accepts both dependencies.
2. Blank input throws `IllegalArgumentException` without calling the policy or sender.
3. Policy rejects the recipient → returns before building any message.
4. When allowed, the code builds a `SimpleMailMessage` with the fields under test.
5. Calls `mailSender.send(message)`—the **transport boundary**.

In production, `billing@example.test` must be replaced with an authorized `From` address/domain; `.test` is purely example data. Production services also require authentication/authorization, template versioning, error policies, and an outbox if post-commit durability is needed; none of those are necessary while practicing message mocking.

### Do Not Swallow Exceptions to Fake Success

We intentionally do **not** write:

~~~java
try {
    mailSender.send(message);
} catch (Exception ignored) {
    System.out.println("Email delivered");
}
~~~

If transport fails, reporting "delivered" is completely unfounded. In an outbox model, a dispatcher catches `MailException` and records `RETRY_PENDING`, `FAILED_PERMANENT`, or `SUBMISSION_UNKNOWN` based on evidence; a single `boolean sent` cannot represent every state.

## 7. First Unit Test with MockitoExtension

**`src/test/java/com/example/mail/ReceiptMailServiceTest.java`**

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class ReceiptMailServiceTest {

    @Mock
    JavaMailSender mailSender;

    @Mock
    RecipientPolicy recipientPolicy;

    @InjectMocks
    ReceiptMailService service;

    @Captor
    ArgumentCaptor<SimpleMailMessage> messageCaptor;

    @Test
    void createsExpectedReceiptAndInvokesMailSenderOnce() {
        String to = "buyer@example.test";
        when(recipientPolicy.canReceiveTransactionalMail(to))
                .thenReturn(true);

        service.sendReceipt(to, "order-184");

        verify(mailSender).send(messageCaptor.capture());
        verifyNoMoreInteractions(mailSender);

        SimpleMailMessage actual = messageCaptor.getValue();
        assertEquals("billing@example.test", actual.getFrom());
        assertEquals("support@example.test", actual.getReplyTo());
        assertEquals(1, actual.getTo().length);
        assertEquals(to, actual.getTo()[0]);
        assertEquals(
                "Receipt for order order-184",
                actual.getSubject());
        assertEquals(
                "Your order order-184 has been recorded.",
                actual.getText());
    }
}
~~~

### Meaning of Annotations

| Annotation | Role |
| --- | --- |
| `@ExtendWith(MockitoExtension.class)` | Initializes and manages Mockito mocks in JUnit 5 |
| `@Mock` | Creates a mock instance for a dependency |
| `@InjectMocks` | Injects mocks into the service's constructor/fields |
| `@Captor` | Initializes an `ArgumentCaptor` |
| `@Test` | Marks a test method |

In this example, `ReceiptMailService` runs without a Spring container; Mockito instantiates the service and injects the mocks. This is a **pure unit test**: ideal for running on every pull request.

### Meaning of Each Assertion

- `verify(mailSender).send(messageCaptor.capture())`: `send(SimpleMailMessage)` was called once (Mockito's default verification count).
- `verifyNoMoreInteractions(mailSender)`: no **other** interaction occurred on the mock sender beyond the verified call.
- `assertEquals(...)`: message fields match expectations.
- No assertion tests opening a TCP socket or receiving an SMTP `250`.

### Why Stub RecipientPolicy?

On a Mockito mock, a method returning `boolean` returns `false` by default. If you forget:

~~~java
when(recipientPolicy.canReceiveTransactionalMail(to))
        .thenReturn(true);
~~~

the service takes the non-sending branch, and `verify(mailSender).send(...)` fails. That is a **fixture setup** mistake, not evidence of an SMTP provider issue.

## 8. Using verify, times, never, and verifyNoInteractions

Mockito offers several ways to check interactions:

~~~java
verify(mailSender).send(any(SimpleMailMessage.class));
verify(mailSender, times(1))
        .send(any(SimpleMailMessage.class));
verify(mailSender, never())
        .send(any(SimpleMailMessage.class));
verifyNoInteractions(mailSender);
~~~

These statements are **independent examples**—never put all four into a single test that called the sender, since `times(1)` and `never()` contradict each other.

| Call | When to Use |
| --- | --- |
| `verify(mock).method(...)` | Assert exactly one invocation with matching arguments |
| `verify(mock, times(n))` | Assert exactly `n` invocations |
| `verify(mock, never())` | Assert a specific overload/argument was never called |
| `verifyNoInteractions(mock)` | Assert zero calls of any kind on the mock |
| `verifyNoMoreInteractions(mock)` | Assert no unverified interactions remain |
| `ArgumentCaptor` | Capture passed objects and assert their properties |

Do not sprinkle `verifyNoMoreInteractions()` mechanically into every test if unrelated changes would make tests brittle. Use it only when **the absence of extra calls** is genuinely required.

### Avoid Verifying the Wrong Overload

`JavaMailSender` defines overloads such as:

~~~java
send(SimpleMailMessage message)
send(SimpleMailMessage... messages)
send(MimeMessage mimeMessage)
send(MimeMessage... mimeMessages)
send(MimeMessagePreparator mimeMessagePreparator)
~~~

`verify(sender).send(any(SimpleMailMessage.class))` **does not automatically match every overload**. Know whether each path uses `SimpleMailMessage`, `MimeMessage`, or `MimeMessagePreparator`. When verifying varargs or arrays, pick a matcher/captor matching the invoked signature.

## 9. Unit Testing the Suppressed-Send Branch

An important practice test: policy forbids sending transactional mail to a recipient.

~~~java
package com.example.mail;

import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class ReceiptMailSuppressionTest {

    @Mock
    JavaMailSender mailSender;

    @Mock
    RecipientPolicy recipientPolicy;

    @InjectMocks
    ReceiptMailService service;

    @Test
    void doesNotSendWhenPolicyDisallowsRecipient() {
        String to = "blocked@example.test";
        when(recipientPolicy.canReceiveTransactionalMail(to))
                .thenReturn(false);

        service.sendReceipt(to, "order-184");

        verify(recipientPolicy)
                .canReceiveTransactionalMail(to);
        verifyNoInteractions(mailSender);
    }
}
~~~

**What is proven:** when the mocked policy returns `false`, the service never calls `JavaMailSender`. This is a valuable business invariant.

**What is not proven:** that every other sending path in the system—such as worker retries, manual replays, or provider fallbacks—checks the same policy. To ensure no bypass path exists, add integration tests at those workflow boundaries.

## 10. Validation Tests: Invalid Inputs Never Touch the Sender

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verifyNoInteractions;

import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import static org.mockito.Mockito.mock;

class ReceiptMailValidationTest {

    @Test
    void rejectsBlankRecipientWithoutSending() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);
        ReceiptMailService service =
                new ReceiptMailService(sender, policy);

        assertThrows(IllegalArgumentException.class,
                () -> service.sendReceipt(" ", "order-184"));

        verifyNoInteractions(sender, policy);
    }

    @Test
    void rejectsMissingOrderIdWithoutSending() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);
        ReceiptMailService service =
                new ReceiptMailService(sender, policy);

        assertThrows(IllegalArgumentException.class,
                () -> service.sendReceipt(
                        "buyer@example.test", null));

        verifyNoInteractions(sender, policy);
    }
}
~~~

These tests verify the **blank/null guards** in the example. They do not validate RFC email syntax, DNS records, or mailbox existence; if your project uses `InternetAddress` or Bean Validation, test that validator separately and never call it a deliverability test.

## 11. Simulating MailException

In production, SMTP calls can fail due to connections, authentication, relay policies, recipients, or timeouts. In unit tests, the mock throws an **intentional exception**:

**`src/test/java/com/example/mail/ReceiptMailServiceFailureTest.java`**

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.mail.MailSendException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class ReceiptMailServiceFailureTest {

    @Test
    void propagatesSenderFailure() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);
        ReceiptMailService service =
                new ReceiptMailService(sender, policy);

        String to = "buyer@example.test";
        when(policy.canReceiveTransactionalMail(to))
                .thenReturn(true);

        doThrow(new MailSendException(
                "Simulated SMTP failure"))
                .when(sender)
                .send(any(SimpleMailMessage.class));

        assertThrows(MailSendException.class,
                () -> service.sendReceipt(to, "order-184"));

        verify(sender, times(1))
                .send(any(SimpleMailMessage.class));
    }
}
~~~

`JavaMailSender.send(...)` returns `void`, so the standard Mockito syntax to stub an exception is `doThrow(...).when(sender).send(...)`.

### Proper Interpretation of the Test

The test proves that the **mock-thrown** exception propagates through the service as expected. It does not prove real-world `MailSendException` instances always carry identical details or phases. Never assume every `MailException` is transient and retryable.

### Error Classification Must Be Tested at the Right Layer

An architecture may have a `MailTransportAdapter` normalizing errors into:

~~~text
NETWORK_TEMPORARY
SMTP_AUTH_FAILURE
RECIPIENT_PERMANENT
CONTENT_REJECTED
SUBMISSION_UNKNOWN
~~~

Retry-policy unit tests can take these categories as inputs. However, **adapter tests** need simulated SMTP replies at exact phases (`EHLO`, `AUTH`, `RCPT TO`, `DATA`) to verify real classification.

## 12. Recognizing the Boundary Between MailException and MessagingException

When composing MIME:

- `MimeMessageHelper` or Jakarta Mail operations can throw `jakarta.mail.MessagingException`.
- `JavaMailSender.send(...)` normally reports transport failures via `org.springframework.mail.MailException` and its subtypes.

Within the same service, distinguish **message-building failures** from **sending failures**:

~~~text
Template model -> MIME creation -> JavaMailSender -> SMTP
       |                |                |
  business error   MessagingException   MailException
~~~

Specific exception classes vary by code, dependencies, and transport. Tests should never simply `catch (Exception)` and mark `SENT`. If parsing/validation fails before transport, **never record an SMTP attempt failure** when no connection was even attempted.

## 13. Moving to HTML: Why Do You Need a Real MimeMessage?

`SimpleMailMessage` suits plain text. For HTML, plain-text alternatives, attachments, or inline resources, use `MimeMessage` and `MimeMessageHelper`:

~~~java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(mime, true, "UTF-8");
helper.setText(
        "Your receipt is ready.",
        "<html><body><p>Your receipt is ready.</p></body></html>"
);
sender.send(mime);
~~~

If you mock `JavaMailSender` without stubbing `createMimeMessage()`, Mockito returns **null** because it is an object-returning method. Passing null into `MimeMessageHelper` breaks the test fixture rather than proving production MIME fails.

### What Should a MIME Test Mock?

**Mock the send step** (`JavaMailSender.send`) while **creating a real `MimeMessage`** so you can inspect headers, multiparts, charsets, and real attachments.

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
Session session = Session.getInstance(new Properties());
when(sender.createMimeMessage())
        .thenAnswer(invocation -> new MimeMessage(session));
~~~

This opens no SMTP connection. It uses an in-memory Jakarta Mail session, hands the `MimeMessage` to the mock, and captures the object for inspection.

## 14. Writing HtmlReceiptMailService with an Attachment

**`src/main/java/com/example/mail/HtmlReceiptMailService.java`**

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class HtmlReceiptMailService {

    private final JavaMailSender mailSender;
    private final RecipientPolicy recipientPolicy;

    public HtmlReceiptMailService(
            JavaMailSender mailSender,
            RecipientPolicy recipientPolicy) {
        this.mailSender = mailSender;
        this.recipientPolicy = recipientPolicy;
    }

    public void sendReceipt(
            String recipient,
            String orderId) throws MessagingException {

        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient must not be blank");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "Order ID must not be blank");
        }
        if (!recipientPolicy.canReceiveTransactionalMail(recipient)) {
            return;
        }

        MimeMessage mime = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("billing@example.test");
        helper.setReplyTo("support@example.test");
        helper.setTo(recipient);
        helper.setSubject("Receipt for order " + orderId);

        String plain = "Your receipt for " + orderId + " is ready.";
        String html = "<html><body><p>Your receipt for "
                + orderId + " is ready.</p></body></html>";

        // In real applications, escape data before inserting into HTML.
        helper.setText(plain, html);

        byte[] receipt = ("Receipt: " + orderId)
                .getBytes(StandardCharsets.UTF_8);
        helper.addAttachment(
                "receipt.txt",
                new ByteArrayResource(receipt),
                "text/plain");

        mailSender.send(mime);
    }
}
~~~

### Key Points

- The real `MimeMessage` holds the MIME data structure.
- `MimeMessageHelper(..., true, "UTF-8")` enables multipart and sets the encoding.
- `helper.setText(plain, html)` creates both a **plain-text alternative and an HTML version**.
- `ByteArrayResource` yields a fresh stream from bytes when needed, fitting small fixtures.
- `addAttachment` attaches the file to MIME.
- `mailSender.send(mime)` is the call mocked in unit tests.

**Security:** the illustrative code concatenates `orderId` directly into HTML for simplicity. Production code must escape values or render via an auto-escaping template engine; never concatenate untrusted user content into HTML. Testing MIME structure does not replace XSS/content validation.

### Do Not Use Real Data in Practice Exercises

`receipt.txt` is a synthetic in-memory file. Never use real invoices or real tokens. For large attachments, enforce byte/memory caps, content-type checks, malware scanning, and proper retention; this practice project verifies MIME composition only.

## 15. Testing MimeMessage with a Mock Sender and Jakarta Mail Session

**`src/test/java/com/example/mail/HtmlReceiptMailServiceTest.java`**

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

class HtmlReceiptMailServiceTest {

    @Test
    void createsMimeMessageAndInvokesSender() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);

        when(policy.canReceiveTransactionalMail(
                "buyer@example.test")).thenReturn(true);

        Session session = Session.getInstance(new Properties());
        when(sender.createMimeMessage())
                .thenAnswer(invocation -> new MimeMessage(session));

        HtmlReceiptMailService service =
                new HtmlReceiptMailService(sender, policy);

        service.sendReceipt("buyer@example.test", "order-184");

        ArgumentCaptor<MimeMessage> captor =
                ArgumentCaptor.forClass(MimeMessage.class);
        verify(sender).send(captor.capture());
        verify(sender).createMimeMessage();

        MimeMessage actual = captor.getValue();
        actual.saveChanges();

        assertEquals(
                "Receipt for order order-184",
                actual.getSubject());
        assertEquals(
                "buyer@example.test",
                actual.getRecipients(Message.RecipientType.TO)[0]
                        .toString());
        assertEquals(
                "billing@example.test",
                actual.getFrom()[0].toString());
        assertTrue(actual.isMimeType("multipart/*"));
    }
}
~~~

### Why Is `saveChanges()` Needed?

`MimeMessage.saveChanges()` finalizes/generates MIME headers and prepares serialization in tests without sending the message. Using a real `MimeMessage` lets you assert headers and content structure rather than merely verifying `MimeMessageHelper` calls.

### This Test Is Incomplete on Its Own

It checks only Subject, recipient, sender, and multipart presence. `isMimeType("multipart/*")` returning true does not prove both **text/plain** and **text/html** exist or that attachment bytes match. Next, we walk the MIME tree to check those contents.

## 16. Traversing the Multipart Tree Instead of Guessing Part Indexes

A MIME message can have multiple nested layers:

~~~text
multipart/mixed
  |
  +-- multipart/related or multipart/alternative
  |      |
  |      +-- text/plain
  |      +-- text/html
  |
  +-- text/plain attachment: receipt.txt
~~~

When code uses `MimeMessageHelper` with mixed/related nesting, `getBodyPart(0)` is not guaranteed to be `text/plain`. **Never write brittle tests assuming HTML is always part index 1.**

A recursive helper collects leaf parts:

**`src/test/java/com/example/mail/MailTestSupport.java`**

~~~java
package com.example.mail;

import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.util.ArrayList;
import java.util.List;

public final class MailTestSupport {

    private MailTestSupport() {
    }

    public record MimeParts(
            List<String> plainBodies,
            List<String> htmlBodies,
            List<String> attachmentNames) {
    }

    public static MimeParts inspect(Part root) throws Exception {
        List<String> plain = new ArrayList<>();
        List<String> html = new ArrayList<>();
        List<String> attachments = new ArrayList<>();
        collect(root, plain, html, attachments);
        return new MimeParts(plain, html, attachments);
    }

    private static void collect(
            Part part,
            List<String> plain,
            List<String> html,
            List<String> attachments) throws Exception {

        if (part.isMimeType("multipart/*")) {
            Multipart multipart = (Multipart) part.getContent();
            for (int i = 0; i < multipart.getCount(); i++) {
                collect(multipart.getBodyPart(i),
                        plain, html, attachments);
            }
            return;
        }

        if (Part.ATTACHMENT.equalsIgnoreCase(
                part.getDisposition())) {
            attachments.add(part.getFileName());
            return;
        }

        if (part.isMimeType("text/plain")) {
            plain.add((String) part.getContent());
        } else if (part.isMimeType("text/html")) {
            html.add((String) part.getContent());
        }
    }
}
~~~

This helper is for simple fixtures. Production MIME may include nested `message/rfc822`, inline resources, attachments lacking disposition headers, and streaming parts; if tests cover those, extend the recursion and classification logic. Never reuse this helper as a security parser for untrusted incoming emails.

## 17. Asserting Plain Text, HTML, and Attachment Name

Add to the MIME test:

~~~java
MailTestSupport.MimeParts parts =
        MailTestSupport.inspect(actual);

assertEquals(1, parts.plainBodies().size());
assertEquals(1, parts.htmlBodies().size());
assertEquals(1, parts.attachmentNames().size());

assertEquals(
        "Your receipt for order-184 is ready.",
        parts.plainBodies().get(0));

assertEquals(
        "<html><body><p>Your receipt for order-184 "
                + "is ready.</p></body></html>",
        parts.htmlBodies().get(0));

assertEquals("receipt.txt",
        parts.attachmentNames().get(0));
~~~

With `MimeMessageHelper.setText(plain, html)`, plain text and HTML are two representations of the same message; check charset, headers, and layout too when business-critical. Never ignore plain text just because UI previews render HTML.

### Inspecting Attachment Bytes

Matching the filename does not prove the file content is intact. A recursive helper for attachment bytes:

~~~java
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import java.io.IOException;

static byte[] findAttachment(Part part, String filename)
        throws Exception {
    if (part.isMimeType("multipart/*")) {
        Multipart multipart = (Multipart) part.getContent();
        for (int i = 0; i < multipart.getCount(); i++) {
            byte[] result = findAttachment(
                    multipart.getBodyPart(i), filename);
            if (result != null) {
                return result;
            }
        }
        return null;
    }

    if (Part.ATTACHMENT.equalsIgnoreCase(
            part.getDisposition())
            && filename.equals(part.getFileName())) {
        try (var stream = part.getInputStream()) {
            return stream.readAllBytes();
        }
    }
    return null;
}
~~~

And:

~~~java
assertArrayEquals(
        "Receipt: order-184".getBytes(
                java.nio.charset.StandardCharsets.UTF_8),
        findAttachment(actual, "receipt.txt"));
~~~

These `findAttachment` snippets are test helpers; place them in the test class or support class with matching visibility and imports. Test fixtures are small, so `readAllBytes()` is fine. **Never read unbounded user attachments entirely into memory** in production code.

## 18. Testing HTML Escaping as an Independent Requirement

A MIME test can pass even when the HTML is unsafe:

~~~java
String html = "<p>Hello " + customerName + "</p>";
~~~

If `customerName` contains HTML characters, the content can be altered unexpectedly. With an auto-escaping Spring template engine or appropriate encoder, test that:

- Text values are escaped for HTML context.
- URL attributes are validated/encoded and disallow dangerous schemes.
- Users cannot inject scripts, active HTML, or remote resources.
- Template strings from untrusted sources never become executable instructions.

A template renderer unit test can verify the escaped output, and the MIME test verifies that output lands inside `text/html`. **Mocking `JavaMailSender` does not protect against HTML injection on its own.**

## 19. Do Not Use @SpringBootTest for Every Unit Test

Constructor injection:

~~~java
JavaMailSender sender = mock(JavaMailSender.class);
RecipientPolicy policy = mock(RecipientPolicy.class);
ReceiptMailService service =
        new ReceiptMailService(sender, policy);
~~~

is sufficient to test service logic. `@SpringBootTest` initializes far more beans, slows down runs, and can pull in unnecessary external config. Never spin up a full Spring context just to use Mockito.

### When Is a Spring Context Test Needed?

When verifying:

- `@Configuration` selects the right implementation.
- Bean qualifiers and routing across multiple mail senders.
- Configuration properties binding.
- Transaction interceptors and application events.
- Async scheduling and outbox integration.

A context test with a mocked `JavaMailSender` is still **wiring/integration around a mock**, not SMTP transport integration.

## 20. Using @MockitoBean / @MockBean in a Spring Context

In Spring Framework versions supporting `@MockitoBean`, you can replace the sender bean in the application context:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class ReceiptContextTest {

    @MockitoBean
    JavaMailSender mailSender;

    @Autowired
    ReceiptMailService receiptMailService;

    @Test
    void applicationServiceUsesInjectedSender() {
        // Test fixture must configure RecipientPolicy
        // to allow the test recipient.
        receiptMailService.sendReceipt(
                "buyer@example.test", "order-184");

        verify(mailSender)
                .send(any(SimpleMailMessage.class));
    }
}
~~~

This is an **illustrative skeleton**: the context must contain a `ReceiptMailService` bean and a suitable `RecipientPolicy`, such as a test configuration registration. The example service class lacks `@Service` so it is not component-scanned automatically. To run this test in a Spring context, register the service and policy via appropriate configuration or annotations.

On older Spring Boot versions, use `@MockBean` instead of `@MockitoBean`, depending on library versions and deprecation status. **Do not mix newer annotations into older projects** without checking compatibility.

### Warning on Test Scope

`@SpringBootTest` does not automatically make a test an SMTP end-to-end test. When the transport bean is mocked, no socket is opened by the sender. Name the test `applicationServiceUsesInjectedSender`, not `mailDeliveredToRecipient`.

## 21. Extra Exercise: Testing Reply-To, Cc, and Bcc

For `SimpleMailMessage`, `Reply-To`, `Cc`, and `Bcc` require explicit tests when used by business rules.

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("billing@example.test");
message.setReplyTo("support@example.test");
message.setTo("buyer@example.test");
message.setCc("accounting@example.test");
message.setBcc("audit@example.test");
message.setSubject("Receipt");
message.setText("Your receipt is ready.");
~~~

Captor assertions:

~~~java
assertArrayEquals(
        new String[] { "buyer@example.test" },
        actual.getTo());
assertArrayEquals(
        new String[] { "accounting@example.test" },
        actual.getCc());
assertArrayEquals(
        new String[] { "audit@example.test" },
        actual.getBcc());
assertEquals(
        "support@example.test",
        actual.getReplyTo());
~~~

Here `actual` is the `SimpleMailMessage` obtained from the test's `ArgumentCaptor`. `assertArrayEquals` is statically imported from `org.junit.jupiter.api.Assertions`.

### What Bcc Tests Do Not Prove

In real SMTP, `Bcc` recipients belong in the **SMTP envelope** and must not be leaked in delivered headers. Asserting `getBcc()` on `SimpleMailMessage` only checks that the service set the field; it does not prove the SMTP client emits proper `RCPT TO` commands or that delivered MIME omits `Bcc`. To test that, use a local SMTP server/transport fixture that inspects envelope and headers separately.

### Be Careful with Multiple Recipients

If a service sends one email with multiple `To`/`Cc`/`Bcc` addresses, individual recipients may be accepted or rejected differently. A mock sender knows nothing about per-recipient outcomes; never conclude "everyone received it" from `verify(sender).send(message)`.

## 22. Testing Multiple Emails Created in a Batch

Suppose a service processes a list of notifications. Two implementation patterns exist:

**Approach A: call `send(message)` per item**

~~~java
for (SimpleMailMessage message : messages) {
    mailSender.send(message);
}
~~~

Tests can capture every call:

~~~java
ArgumentCaptor<SimpleMailMessage> captor =
        ArgumentCaptor.forClass(SimpleMailMessage.class);

verify(mailSender, times(2)).send(captor.capture());
assertEquals(2, captor.getAllValues().size());
~~~

**Approach B: call the varargs overload once**

~~~java
mailSender.send(messages.toArray(
        new SimpleMailMessage[0]));
~~~

Here, a single `send(SimpleMailMessage... messages)` invocation carries multiple items. The test must verify the exact overload/array invoked by the service:

~~~java
ArgumentCaptor<SimpleMailMessage[]> batchCaptor =
        ArgumentCaptor.forClass(SimpleMailMessage[].class);

verify(mailSender).send(batchCaptor.capture());
assertEquals(2, batchCaptor.getValue().length);
~~~

These snippets represent **alternative implementations** and belong inside test classes defining the corresponding `messages` and `mailSender` variables.

### Mockito, Varargs, and Overloaded Methods

Mockito's varargs matching changed across major versions. With array overloads, use `ArgumentCaptor<SimpleMailMessage[]>` or match the passed array with explicit types/overloads for your Mockito version. If `verify` does not match, check the actual invocation and method signature—**never weaken assertions to a meaningless `verifyNoMoreInteractions` just to make the test pass**.

### Note: A Batch Method Does Not Guarantee All-or-Nothing

Mocks do not execute SMTP, so `send(array)` does not reveal whether earlier messages were already accepted when a later message fails. To test partial failures, use adapter integration tests and per-notification/recipient state tracking.

## 23. Testing with MimeMessagePreparator

`JavaMailSender` supports sending via `MimeMessagePreparator`: the application passes a callback to populate the message, and the sender creates the `MimeMessage` and invokes the callback.

A service:

~~~java
package com.example.mail;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class PreparedNoticeService {

    private final JavaMailSender sender;

    public PreparedNoticeService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendNotice(String recipient, String text) {
        sender.send(mime -> {
            MimeMessageHelper helper =
                    new MimeMessageHelper(mime, "UTF-8");
            helper.setFrom("notices@example.test");
            helper.setTo(recipient);
            helper.setSubject("Notification");
            helper.setText(text);
        });
    }
}
~~~

If you only write:

~~~java
verify(sender).send(any(MimeMessagePreparator.class));
~~~

you prove a callback was passed to the mock, **not that the callback ran and populated the message properly**. A Mockito mock never executes callbacks automatically.

### Using doAnswer to Invoke the Preparator on a Real MIME Message

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessagePreparator;

class PreparedNoticeServiceTest {

    @Test
    void invokesPreparatorAndBuildsExpectedMime()
            throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        AtomicReference<MimeMessage> captured =
                new AtomicReference<>();

        doAnswer(invocation -> {
            MimeMessagePreparator preparator =
                    invocation.getArgument(0);

            MimeMessage realMime = new MimeMessage(
                    Session.getInstance(new Properties()));
            preparator.prepare(realMime);
            realMime.saveChanges();
            captured.set(realMime);
            return null;
        }).when(sender).send(any(MimeMessagePreparator.class));

        PreparedNoticeService service =
                new PreparedNoticeService(sender);
        service.sendNotice(
                "buyer@example.test", "Your order is ready.");

        verify(sender).send(any(MimeMessagePreparator.class));
        MimeMessage actual = captured.get();

        assertEquals("Notification", actual.getSubject());
        assertEquals(
                "buyer@example.test",
                actual.getRecipients(Message.RecipientType.TO)[0]
                        .toString());
        assertEquals(
                "Your order is ready.",
                actual.getContent().toString());
    }
}
~~~

This tests **callback preparation** with a real MIME message without calling SMTP. Notice how `doAnswer` targets the `send(MimeMessagePreparator)` overload explicitly.

### When Should You Use doAnswer?

When important behavior lives inside a callback or deferred closure, `verify(callback passed)` is not enough. You can invoke the callback in the test and assert its result. Still, be clear that this is **test-simulated execution**, not a real `JavaMailSender` sending mail.

## 24. Avoid Tests Depending on an SMTP Host or the Internet

The unit under test:

~~~java
ReceiptMailService service =
        new ReceiptMailService(mockSender, mockPolicy);
~~~

does not require:

~~~text
SMTP_HOST
SMTP_USERNAME
SMTP_PASSWORD
VPN
Internet access
~~~

Network-dependent tests lead to:

- Flaky CI from DNS, TLS, or provider outages.
- Accidental emails sent to real people.
- Distributing secrets where they are not needed.
- Hard-to-reproduce failures.
- Slow tests that lose unit-test isolation.

Focus on **deterministic inputs, outputs, and mocks**. When testing SMTP transport, create a separate suite using a fake SMTP server or an authorized provider sandbox.

### Critical CI Guardrail

If the project has a configuration profile pointing to production SMTP, unit tests **must never** activate that profile. Mockito unit tests do not start a Spring context, keeping them safe from auto-configured transport. For context tests, ensure the mail sender bean is replaced by a mock or pointed to a controlled test server.

## 25. Keep Test Data Separate from Customer Data

Addresses under the reserved `.test` domain work well for test fixtures:

~~~text
buyer@example.test
blocked@example.test
support@example.test
billing@example.test
~~~

They serve purely as fixtures. Never send to these addresses over real SMTP expecting live mailboxes; `.test` is not production mail infrastructure.

Use fake order IDs, fake names, and small in-memory attachments. Never copy raw production emails, OTPs, passwords, or sensitive data into test resources.

### Dynamic Dates and Test Determinism

If the subject contains a date, never call `LocalDate.now()` directly in the service and assert against the CI environment's date. Inject a `Clock`:

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
        java.time.Instant.parse("2026-11-20T02:00:00Z"),
        ZoneOffset.UTC);
LocalDate date = LocalDate.now(fixed);
~~~

Tests can then predict exact subjects and bodies. `Clock.fixed` only controls application time; it does not test real mail delivery.

## 26. Retry Exercise: One Call in a Test Does Not Mean Exactly-Once

This test:

~~~java
verify(sender, times(1)).send(any(SimpleMailMessage.class));
~~~

proves one call in **a single test execution**. In production, the following can happen:

~~~text
Worker A calls SMTP
Relay accepts message
Worker A crashes before updating database
Queue redelivers notification
Worker B calls SMTP again
~~~

Unit mocks on an isolated service never catch this failure mode. Testing duplicate prevention across restarts requires:

- A durable outbox/ledger with an idempotency key.
- Atomic claims or leases across workers.
- Attempt tracking.
- Proper transaction boundaries between database and SMTP.
- Handling `SUBMISSION_UNKNOWN` when relay acceptance is uncertain.
- Integration tests simulating worker crashes and queue redeliveries.

### Unit Test Goal for Retry Policy

A small policy class can decide:

~~~java
package com.example.mail;

public final class RetryPolicy {
    public boolean shouldRetry(
            FailureKind failure,
            int attempts,
            int maxAttempts,
            boolean expired) {
        return !expired
                && attempts < maxAttempts
                && failure == FailureKind.TEMPORARY;
    }
}

enum FailureKind {
    TEMPORARY,
    PERMANENT,
    AUTHENTICATION,
    UNKNOWN_OUTCOME
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class RetryPolicyTest {

    private final RetryPolicy policy = new RetryPolicy();

    @Test
    void retriesOnlyTemporaryFailuresWithinBudget() {
        assertTrue(policy.shouldRetry(
                FailureKind.TEMPORARY, 1, 3, false));
        assertFalse(policy.shouldRetry(
                FailureKind.PERMANENT, 1, 3, false));
        assertFalse(policy.shouldRetry(
                FailureKind.AUTHENTICATION, 1, 3, false));
        assertFalse(policy.shouldRetry(
                FailureKind.UNKNOWN_OUTCOME, 1, 3, false));
        assertFalse(policy.shouldRetry(
                FailureKind.TEMPORARY, 3, 3, false));
        assertFalse(policy.shouldRetry(
                FailureKind.TEMPORARY, 1, 3, true));
    }
}
~~~

This is **pure policy logic** needing no SMTP mocks. What remains unproven here is whether the real adapter classifies exceptions accurately into `FailureKind` and whether the worker persists `availableAt` properly; that belongs in integration tests.

## 27. Testing That Expired Messages Are Never Sent

For OTP or reminder emails, expiration is a business rule:

~~~java
if (!clock.instant().isBefore(notification.expiresAt())) {
    repository.markExpired(notification.id());
    return;
}
mailSender.send(message);
~~~

In a unit test:

1. Inject `Clock.fixed` past `expiresAt`.
2. Stub the repository to return the matching notification.
3. Invoke the worker.
4. Verify `markExpired(id)`.
5. Verify `mailSender` has zero send invocations.

### Why Is This Still a Mock Test?

It proves a worker will not **request a send** when expired under simulated conditions. To ensure no secondary sending path in production bypasses this guard or runs on a stale snapshot, add integration tests covering transactions and versions.

## 28. Testing an Outbox: Business Services Should Not Send Directly

In a system with business transactions, you can design:

~~~text
confirmPayment()
    |
    +-- update payment status in database
    |
    +-- insert mail outbox record
    |
    +-- COMMIT

background worker:
    claim due outbox record
    render and send via JavaMailSender
    store submission outcome
~~~

In this architecture, a test asserting:

~~~java
verify(mailSender).send(any(SimpleMailMessage.class));
~~~

**right after `confirmPayment()`** signals a design flaw, because the payment service should not invoke SMTP inside the transaction. A better unit test asserts:

~~~java
verify(outboxRepository).insert(any(MailOutboxRecord.class));
verifyNoInteractions(mailSender);
~~~

`MailOutboxRecord` and `outboxRepository` are **illustrative domain names**, not built-in Spring Mail classes. The snippet shows what to verify.

### Verifying Different Things at Each Boundary

| Component | What to Mock | Assert |
| --- | --- | --- |
| Payment service | Outbox repository | Correct mail intent recorded; zero SMTP calls in transaction |
| Notification renderer | Template engine / data source | Accurate body and MIME |
| Mail dispatch worker | `JavaMailSender` | Sender invoked when job is eligible |
| Retry handler | Repository + failure classifier | Appropriate state and `availableAt` persisted |
| Provider event consumer | Event repository | Delivery projection updated after verified event |

Never try to use a single `JavaMailSender` mock to prove the entire workflow from payment to Inbox. Each boundary has its own evidence.

## 29. Transactions and @Async: What Mocks Do Not Guarantee

A method:

~~~java
@Async
public void sendLater(String to) {
    mailSender.send(buildMessage(to));
}
~~~

may execute on another thread. If a unit test calls the object directly rather than through a Spring proxy, `@Async` creates no thread; if called through a real proxy, immediate assertions may execute **before** the send runs.

### Picking the Right Test Layer

- Pure unit tests: invoke the method directly to verify synchronous logic.
- Context integration tests: test real `@Async`/proxy/executor wiring using reliable synchronization rather than arbitrary `Thread.sleep`.
- Durable scheduling tests: test outbox/queue persistence across process restarts.

`@Async` does not persist jobs durably. A passing mock test does not prove an email will still be sent if the JVM dies before the async task executes.

### Tests Should Never Sleep Arbitrarily

~~~java
Thread.sleep(500);
verify(mailSender).send(any(SimpleMailMessage.class));
~~~

This easily flakes under heavy CI load. When integration tests truly verify async execution, use `CompletableFuture`, latches, Awaitility, or completion status with explicit timeouts—never sleep a fixed number of milliseconds and guess.

## 30. Using Captors for Immutable Messages and Avoiding Post-Send Mutation

Mockito captures the **object reference** passed into a call. If the service mutates the same `SimpleMailMessage` instance after calling `send(message)`, the captor at the end of the test sees the **post-mutation** state rather than the state at send time.

Anti-pattern:

~~~java
mailSender.send(message);
message.setTo("other@example.test");
~~~

The test:

~~~java
verify(mailSender).send(captor.capture());
~~~

would observe the modified recipient. To capture a snapshot at invocation time, use `doAnswer` to copy the object inside the callback:

~~~java
java.util.concurrent.atomic.AtomicReference<SimpleMailMessage>
        snapshot = new java.util.concurrent.atomic.AtomicReference<>();

doAnswer(invocation -> {
    SimpleMailMessage input = invocation.getArgument(0);
    snapshot.set(new SimpleMailMessage(input));
    return null;
}).when(mailSender).send(any(SimpleMailMessage.class));
~~~

Then assert `snapshot.get()`. The copy constructor `SimpleMailMessage(SimpleMailMessage original)` copies message fields at the exact moment the mock is called. For `MimeMessage`, snapshots can be taken via serialized bytes or test-specific immutable extraction, since `MimeMessage` is also mutable.

### When Is a Snapshot Necessary?

Only when the object may be modified or reused after sending, or when you want to assert exact state at invocation time. In our example service where the message is never mutated after sending, a plain `ArgumentCaptor` is enough.

## 31. Mockito Strict Stubbing and Readable Tests

With `MockitoExtension`, strict stubbing catches unused stubs. For example:

~~~java
when(policy.canReceiveTransactionalMail("unused@example.test"))
        .thenReturn(true);
~~~

if the test instead calls `service.sendReceipt("buyer@example.test", ...)`, the stub never matches. The test warns or fails due to inconsistent setup.

Instead of sprinkling `lenient()` everywhere:

- Stub exact test data per test.
- Avoid stubbing methods not called on that branch.
- Put only genuinely shared setup in `@BeforeEach`.
- Split allow and deny branches into separate tests.
- Never turn on `RETURNS_DEEP_STUBS` just to avoid designing clean dependency seams.

### Do Not Mock Too Deeply

If a test contains chains like:

~~~java
when(sender.getSession().getTransport("smtp")
        .isConnected()).thenReturn(true);
~~~

you are mocking deep into transport internals instead of testing service behavior. `JavaMailSender` is already a clean boundary abstraction; testing Jakarta Mail transport internals belongs in integration tests.

## 32. Extracting a Message Builder When Logic Grows Complex

A single service that looks up data, checks recipient eligibility, renders templates, builds attachments, calls SMTP, and updates the database becomes hard to test. Split it:

~~~mermaid
flowchart LR
    A["Business decision"] --> B["MailMessageFactory"]
    B --> C["Prepared MIME"]
    C --> D["JavaMailSender"]
    D --> E["SMTP"]
~~~

Components:

- `RecipientPolicy`: permission to send.
- `MailMessageFactory`: builds the message with proper subject, body, and headers.
- `JavaMailSender`: transport boundary.
- `DeliveryStateRepository`: records submission and attempt states.

**Testing payoff:** the factory can use real Jakarta Mail in tests without mocking a sender; the dispatcher test verifies `sender.send`; policy tests need no MIME at all. Each test answers a clearer question.

### Do Not Refactor Solely for Mocking

For a short service like `ReceiptMailService`, constructor injection and one captor test are sufficient. Introduce extra abstractions only when complexity, reuse, or operational boundaries justify them.

## 33. Negative Test Case: Disallowed Template

Suppose business rules define a `TemplatePolicy`:

~~~java
public interface TemplatePolicy {
    boolean mayUseTemplate(String templateKey);
}
~~~

The service checks:

~~~java
if (!templatePolicy.mayUseTemplate(templateKey)) {
    throw new IllegalArgumentException(
            "Template is not allowed");
}
~~~

The corresponding unit test should:

1. Stub `templatePolicy.mayUseTemplate("unknown")` to return `false`.
2. Assert `assertThrows` when calling the service.
3. Call `verifyNoInteractions(mailSender)`.

The test proves disallowed templates are blocked without sending any mail. If template data contains untrusted HTML or links, test input sanitization and rendering separately.

## 34. Negative Test Case: Invalid Attachment

For emails with attachments, an application may enforce:

- Files belong to a business-approved MIME/extension allowlist.
- File size stays within limits.
- Files passed malware scanning.
- User-supplied filenames or paths are never used as storage paths.
- Contents are loaded by verified version/hash.

In a dispatch-service unit test, mock an `AttachmentPolicy` returning `REJECTED` and verify `JavaMailSender` is never called. To prove real MIME bytes are encoded properly, run a real MIME test. To prove real malware scanning works, run an integration test against the approved scanner; a mocked `CLEAN` verdict does not make an attachment clean.

### Never Treat "MIME Built" as "Scanned"

~~~text
MIME parse/build successful != Malware-free attachment
~~~

Tests must keep their scope clear so security claims remain accurate.

## 35. Summary Table of Assertions by Behavior to Prove

| Requirement | Test Type | Appropriate Assertion |
| --- | --- | --- |
| Right recipient | Unit + mock | `ArgumentCaptor.getTo()` |
| Right `From` / `Reply-To` | Unit + mock | `getFrom()`, `getReplyTo()` |
| Right subject / plain body | Unit + mock | `getSubject()`, `getText()` |
| Blocked recipients never sent | Unit + mock | `verifyNoInteractions(sender)` |
| Blank input rejected | Unit + mock | `assertThrows`, zero interactions |
| Sender error propagated | Unit + mock | `doThrow`, `assertThrows` |
| Sent at most once per call | Unit + mock | `times(1)` |
| Batch of N messages | Unit + mock | Array captor or `getAllValues()` |
| Plain and HTML properly built | MIME unit | Walk MIME tree, inspect decoded content |
| Attachment bytes intact | MIME unit | Part disposition, name, and bytes |
| `Bcc` header omitted from delivered message | SMTP integration | Inspect envelope and transmitted headers |
| TLS/STARTTLS works | SMTP integration | Real handshake with test relay |
| Real relay returns SMTP `250` | SMTP integration | SMTP transcript / server capture |
| Real provider credentials valid | Authorized provider smoke test | Provider acceptance |
| Bounce/delivery events handled | Webhook integration | Signature, dedup, projection |
| Email reaches seed Inbox | Controlled mailbox observation | Seed folder location |
| Recipient opened/read | Product-level confirmation if applicable | Verified user action |

**Never use unit mocks to "fill in" for SMTP, provider, or mailbox results.** Until observed, the accurate state is `UNKNOWN`, not `DELIVERED`.

## 36. Practice Scenarios Matrix

| ID | Scenario | What to Verify |
| --- | --- | --- |
| U01 | Valid recipient, policy allows | One `SimpleMailMessage` with expected fields |
| U02 | Blank recipient | Throws validation error, never calls policy or sender |
| U03 | Blank order ID | Throws validation error, never sends |
| U04 | Policy rejects | Never calls sender |
| U05 | Right `From` identity | Captor checks `From` |
| U06 | Right `Reply-To` | Captor checks `Reply-To` |
| U07 | Subject contains order ID | Captor checks subject |
| U08 | Plain-text body matches | Captor checks text |
| U09 | Single send call | `times(1)` |
| U10 | Simulated SMTP failure | `doThrow`, `assertThrows` |
| U11 | Policy checked once | `verify(policy)` |
| U12 | Retry policy on temporary failure | Allows retry while within budget |
| U13 | Retry policy on permanent failure | Does not retry |
| U14 | Retry policy on unknown outcome | Does not blindly retry |
| U15 | Expired notification | Does not send |
| U16 | Disallowed template | Does not send |
| U17 | Rejected attachment | Never calls sender |
| U18 | Batch sent item-by-item | Captor `getAllValues()` |
| U19 | Batch sent via varargs overload | Array captor and element count |
| U20 | Message mutated after send | Snapshot inside `doAnswer` |
| M01 | Real `MimeMessage` constructed | Stub `createMimeMessage` returns MIME |
| M02 | MIME `From`/`To`/`Subject` | Capture `MimeMessage` and assert |
| M03 | MIME plain alternative | Parse MIME tree |
| M04 | MIME HTML alternative | Parse MIME tree |
| M05 | MIME UTF-8 Unicode | Decoded content preserves characters |
| M06 | Attachment filename | MIME part disposition/name |
| M07 | Attachment bytes | Read test fixture stream |
| M08 | Inline resource (extension) | `Content-ID` and HTML `cid:` match |
| M09 | Preparator callback | `doAnswer` invokes callback |
| M10 | MIME build fails | Zero transport submissions when build aborts |
| I01 | Mockito context with mocked sender | Service wiring without SMTP sockets |
| I02 | Local SMTP receives message | Test relay captures MIME |
| I03 | Local SMTP replies 4xx/5xx | Adapter handles error by phase |
| I04 | Provider delivered webhook | Delivery status from verified event |
| I05 | Unknown SMTP outcome | No automatic resend |

This is a **recommended test matrix**, not a log of executed tests. When reviewing your project, note which cases were coded and which environment ran them; never infer tests passed just by reading code snippets in documentation.

## 37. Advanced Testing: Using @ParameterizedTest for Invalid Input

When multiple inputs share one rule, JUnit 5 reduces boilerplate:

~~~java
package com.example.mail;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.mail.javamail.JavaMailSender;

class ReceiptMailParameterizedTest {

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = { " ", "   " })
    void rejectsBlankRecipients(String recipient) {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);
        ReceiptMailService service =
                new ReceiptMailService(sender, policy);

        assertThrows(IllegalArgumentException.class,
                () -> service.sendReceipt(recipient, "order-184"));

        verifyNoInteractions(sender, policy);
    }
}
~~~

This test verifies null, empty, and whitespace checks—not RFC email syntax or mailbox existence. To test `InternetAddress`, write a dedicated validator test with syntactic inputs.

### Avoid Overstating Assertions

`null`, empty strings, and whitespace are rejected by the current validation. However, a string like `not-an-email` is **not** blocked by `isBlank()`; blocking it requires adding a real email validator to the implementation. **Never write tests expecting every invalid address to be rejected when the service only checks for blankness.**

## 38. When Testing Dynamic Content or Localization

Subjects and bodies may vary by locale:

~~~text
vi-VN: Xác nhận đơn hàng order-184
en-US: Receipt for order order-184
~~~

Unit tests of message composition should supply a `Locale` or a template renderer mock/fixture and capture `SimpleMailMessage`. For real templates, test separately that:

- Vietnamese diacritics are preserved cleanly in MIME.
- Placeholders resolve accurately.
- Plain text and HTML stay semantically consistent.
- Currency and date/time values format per the supplied locale and timezone.
- HTML escaping prevents user data from becoming markup.

A mock sender is not responsible for rendering templates. If you mock both the renderer and the sender, the test verifies only **service orchestration**, not template output. To test template output, use the real renderer or defined snapshots/fixtures.

## 39. Reducing False Positives in Tests

A test can pass without protecting the requirement:

~~~java
verify(sender).send(any(SimpleMailMessage.class));
~~~

If a developer accidentally changes the recipient from `buyer@example.test` to `attacker@example.test`, the test still passes because `any(...)` ignores content.

### Improve with Capturing

~~~java
ArgumentCaptor<SimpleMailMessage> captor =
        ArgumentCaptor.forClass(SimpleMailMessage.class);

verify(sender).send(captor.capture());
assertArrayEquals(
        new String[] { "buyer@example.test" },
        captor.getValue().getTo());
~~~

**Rule of thumb:** use `any(...)` when you only need to prove a call occurred; use a captor or `argThat` when inner properties are business requirements.

### When to Use argThat?

For a simple predicate:

~~~java
verify(sender).send(argThat((SimpleMailMessage msg) ->
        msg.getSubject().startsWith("Receipt for order ")
                && msg.getTo() != null
                && msg.getTo().length == 1));
~~~

For multiple properties, `ArgumentCaptor` is usually more readable and gives clearer failure messages. When using `argThat` with overloaded methods, specify the lambda parameter type as shown so the Java compiler picks the right overload.

### Do Not Assert Unimportant Details

If business rules only require that the subject contains the order ID and the body came from the renderer, avoid asserting every whitespace character of the template inside orchestration unit tests. Keep tests resilient by separating template-content tests from dispatch tests.

## 40. Choosing Test Depth by Risk

| PR Change | Most Valuable Test |
| --- | --- |
| Selecting recipient from order | Policy unit test + captor |
| Changing email subject | Message composition test |
| Adding HTML alternative | MIME parsing test |
| Adding attachment | MIME structure/bytes + security policy |
| Changing sender bean/route | Spring wiring/config test |
| Changing SMTP port/TLS/auth | SMTP integration / staging smoke test |
| Changing provider | Provider auth/events + canary |
| Changing retry policy | Policy unit + dispatch integration |
| Changing outbox claim | Database concurrency integration |
| Changing DKIM/domain | DNS / received-message authentication |
| Improving Inbox placement | Seed tests + production telemetry |

Add tests at the layer where the risk is actually observable rather than multiplying Mockito tests infinitely without expanding proof.

## 41. Notes on Verifying Overloaded send Methods

`JavaMailSender` methods include:

~~~java
void send(SimpleMailMessage simpleMessage);
void send(SimpleMailMessage... simpleMessages);
void send(MimeMessage mimeMessage);
void send(MimeMessage... mimeMessages);
void send(MimeMessagePreparator mimeMessagePreparator);
void send(MimeMessagePreparator... mimeMessagePreparators);
~~~

For example, if the implementation calls:

~~~java
mailSender.send(mimeMessage);
~~~

verification requires:

~~~java
verify(mailSender).send(any(MimeMessage.class));
~~~

not:

~~~java
verify(mailSender).send(any(SimpleMailMessage.class));
~~~

These are distinct message types, and Mockito matches only the exact method signature invoked.

### Stubbing Matching Exceptions

If the code calls `send(MimeMessage)`, stub:

~~~java
doThrow(new MailSendException("simulated"))
        .when(mailSender)
        .send(any(MimeMessage.class));
~~~

Stubbing the `SimpleMailMessage` overload will not apply. When a test unexpectedly "does not throw", check whether you stubbed the wrong overload.

### Use Qualifiers When Multiple JavaMailSender Beans Exist

A Spring context may define a primary transactional sender and a marketing sender. A plain `@Mock` passed via constructor is explicit; with `@MockitoBean` in a context, verify which bean is replaced. When multiple candidates exist, use the appropriate bean name or qualifier for your Spring version so tests do not verify a different mock than the one production uses.

## 42. Testing Error Policies Without Allowing Duplicate Sends

A failure path may look like:

~~~text
Sender throws MailException
  |
  +-- record attempt
  +-- normalize failure
  +-- if temporary and safe: schedule retry
  +-- if permanent: stop
  +-- if unknown outcome: reconcile
~~~

For **unit tests**, a mocked `JavaMailSender` can throw an error while a mocked repository asserts the right state update.

~~~java
doThrow(new MailSendException("temporary-test"))
        .when(sender).send(any(SimpleMailMessage.class));

// Call dispatcher under test, then verify repository
// recorded the state and reason per the supplied policy.
~~~

Keep in mind:

1. A `MailSendException` constructed in Mockito does not prove the error is SMTP `451`/`421` or happened before `DATA`.
2. A socket error after `DATA` may already have been accepted by the relay.
3. Never increment retry counts based solely on `verify(times(1))` while ignoring physical SMTP attempts.
4. Never assume `Message-ID` prevents duplicates across every recipient server.

To test failure phases, use a scripted SMTP server capable of returning specific codes and closing connections at exact protocol phases.

## 43. Adding a Test Ensuring Nothing Sends When Policy Throws

If the policy service fails, the prudent default in sensitive systems is **not sending until authorization is verified**:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class ReceiptPolicyFailureTest {

    @Test
    void stopsBeforeSendingWhenPolicyIsUnavailable() {
        JavaMailSender sender = mock(JavaMailSender.class);
        RecipientPolicy policy = mock(RecipientPolicy.class);
        ReceiptMailService service =
                new ReceiptMailService(sender, policy);

        String to = "buyer@example.test";
        when(policy.canReceiveTransactionalMail(to))
                .thenThrow(new IllegalStateException(
                        "Policy service unavailable"));

        assertThrows(IllegalStateException.class,
                () -> service.sendReceipt(to, "order-184"));

        verifyNoInteractions(sender);
    }
}
~~~

In a real system, a policy outage may be classified so the notification moves to `HOLD` or `RETRY_PENDING` per business rules. The test above proves only that the service **never bypasses the policy** to send when eligibility cannot be confirmed.

## 44. Documenting Test Results Accurately

Instead of reporting:

~~~text
All emails successfully delivered in JUnit tests.
~~~

write:

~~~text
JUnit/Mockito unit tests:
  - Receipt service invoked JavaMailSender with expected fields.
  - Invalid and suppressed recipients caused zero send calls.
  - Simulated MailSendException propagated correctly.
  - MIME message contained plain/HTML alternatives and attachment.

Not measured:
  - Production SMTP connectivity or credentials.
  - Relay acceptance, bounce/delivery outcomes.
  - Inbox placement and human engagement.
~~~

This is a **reporting template**, not output from an actual run. Never claim your tests observed things they did not measure.

### When Displaying Status to End Users

A business flow might track states:

| State | Interpretation |
| --- | --- |
| `QUEUED` | System accepted the request |
| `PROCESSING` | Worker is handling it |
| `SUBMITTED` | Relay/provider accepted submission |
| `DEFERRED` | Provider/receiver temporarily delayed delivery |
| `BOUNCED` | Evidence of non-delivery received |
| `DELIVERED` | Provider/DSN source reported delivered per definition |
| `SUBMISSION_UNKNOWN` | Transport outcome uncertain |
| `INBOX_OBSERVED` | Observed in an authorized seed Inbox |

Mock unit tests must never write `SUBMITTED` or `DELIVERED` into production databases. Those states must originate from actual transport, provider, or recipient observations.

## 45. If Adding SMTP Integration Tests, Open a Separate Suite

Once comfortable with mocks, the next step uses GreenMail, Wiser, Mailpit, or a fake SMTP server capable of capturing mail:

~~~text
ReceiptMailService
      |
      v
JavaMailSenderImpl (real)
      |
      v
Local SMTP test server
      |
      v
Captured MIME + SMTP conversation
~~~

### What Local Integration Tests Add

- Client opens a socket and speaks SMTP to the test server.
- Test server actually receives the message.
- How the SMTP envelope differs from MIME headers.
- Whether MIME serialization works cleanly with Jakarta Mail transport.
- How timeouts, invalid `RCPT`, and simulated AUTH/TLS failures are handled per policy.

### What Remains Unproven

- That production SMTP accounts are active and authorized to send.
- SPF/DKIM/DMARC alignment across the Internet.
- Domain and IP reputation.
- Recipient mailbox routing, spam filtering, and Inbox placement.

**Local SMTP tests are not Internet deliverability tests.** Separate the suites to build layered proof without turning every unit test into a network test.

### Safety Conditions

Never connect to production SMTP while doing exercises; use a local server or authorized provider sandbox. For local servers, bind to `127.0.0.1`, use a dedicated port, synthetic data, and zero real credentials.

## 46. End-to-End Practice Sequence

A coherent workflow:

<escape>1.</escape> **Initialize the project.** Create a Spring Boot app with Mail starter, Spring Boot Test, and Mockito JUnit Jupiter.

<escape>2.</escape> **Define boundaries.** Create `RecipientPolicy` and `ReceiptMailService` using constructor injection.

<escape>3.</escape> **Write the happy-path test.** Stub policy to return true, invoke the service, and capture `SimpleMailMessage`.

<escape>4.</escape> **Assert contents.** Verify `To`, `From`, `Reply-To`, subject, body, and exactly one send call.

<escape>5.</escape> **Write non-sending tests.** Policy returning false and blank inputs must leave the mock sender with zero interactions.

<escape>6.</escape> **Write failure tests.** Configure `doThrow` on `send(SimpleMailMessage)` and assert exception propagation per contract.

<escape>7.</escape> **Create the MIME service.** Use `MimeMessageHelper` with plain text, HTML, and an attachment.

<escape>8.</escape> **Stub the MIME factory.** In tests, have `createMimeMessage()` return `new MimeMessage(Session.getInstance(...))`.

<escape>9.</escape> **Capture and inspect.** Traverse multiparts to read plain text, HTML, and attachments rather than asserting only `multipart/*`.

<escape>10.</escape> **Test negative cases.** Vary recipient/order IDs, make policy throw, simulate bad attachments, and verify guard branches.

<escape>11.</escape> **Report within scope.** Green unit tests mean service logic and MIME composition match assertions, without real SMTP.

<escape>12.</escape> **Extend appropriately.** If the project needs transport proof, add a dedicated local SMTP integration suite.

No running Spring Boot server is needed for pure Mockito tests. Run the suite via Gradle/Maven when practicing; typical commands are:

~~~bash
./gradlew test
~~~

or:

~~~bash
./mvnw test
~~~

On Windows, use the matching wrapper (`gradlew.bat test` or `mvnw.cmd test`). These are **learner commands**, not commands executed while authoring this article.

## 47. Interpreting Test Results Step by Step

When running tests in your project, common outcomes include:

| Symptom | Causes to Check |
| --- | --- |
| `Wanted but not invoked` | Service took a different branch, policy defaulted to false, or wrong overload verified |
| `Too many actual invocations` | Service invoked the sender more times than expected |
| `UnnecessaryStubbingException` | Stub unused; fixture took a different branch |
| `NullPointerException` at `createMimeMessage()` | Mock returned null by default; real MIME factory not stubbed |
| `ClassCastException` parsing MIME part | Test assumed content is `String` or `Multipart` of the wrong type |
| Subject assertion fails | Builder/template logic bug or mismatched test fixture |
| Attachment assertion fails | MIME helper structure, content type, disposition, or bytes differ |
| `NoSuchMethodError` / class loading error | Mixed Jakarta Mail / Spring / Mockito versions |
| Mockito cannot inject | Constructor or bean setup mismatch |
| Network error inside a unit test | Real sender or external dependency left unmocked |
| CI passes but production mail is missing | Tests do not observe SMTP/provider/mailbox; run operational runbook |

### When Mockito Reports Zero Invocations

Check in order:

1. Did input validation throw or return early?
2. Was the policy mock stubbed to return `true`?
3. Did the service receive the **exact mock instance** you are verifying?
4. Did the service call `send(MimeMessage)` or `send(SimpleMailMessage)`?
5. Did the call happen synchronously or on a worker/async thread?
6. Did a branch enqueue to an outbox instead of calling the sender directly?

Never start by adding `lenient()` or relaxing `times(1)` to `atLeastOnce()` to force a green build. Find out what actually happened.

## 48. When MIME Tests Show Multipart but HTML Is Missing

Common causes:

- Service called `helper.setText(plain)` instead of `helper.setText(plain, html)`.
- HTML was mistakenly passed as plain text.
- Test inspected only top-level body parts, skipping nested multiparts.
- A `text/plain` attachment was mistaken for the plain alternative.
- Code aborted before reaching the sender.

A MIME inspector should:

1. Call `saveChanges()` if needed to prepare the message for inspection.
2. Walk the `Multipart` tree recursively.
3. Check `Part.ATTACHMENT` before classifying text parts.
4. Collect `text/plain` and `text/html` by MIME type.
5. Compare decoded content against fixtures.

If production adds inline images, `multipart/related` may nest inside `mixed` alongside `alternative`; never assume exactly two leaf parts.

## 49. When Tests Include Unicode Data

Example of a Vietnamese subject:

~~~java
helper.setSubject("Biên nhận đơn hàng số 184");
helper.setText(
        "Đơn hàng của bạn đã được ghi nhận.",
        "<p>Đơn hàng của bạn đã được ghi nhận.</p>");
~~~

Tests should inspect a real `MimeMessage` and assert `getSubject()` plus decoded plain/HTML text preserve Unicode. Do not rely solely on `verify(sender.send(any()))`, which cannot verify how characters were encoded.

### Avoid Rigid Assertions on Raw MIME Header Text

MIME may choose different encoded-words or transfer encodings while decoding identically. When the goal is preserving reader-visible text, prefer asserting **decoded subject and body**; write separate tests with explicit expectations per Jakarta Mail implementation only when verifying wire header format.

## 50. Common Test Design Mistakes

### 50.1. Mocking the Sender and Claiming Inbox Delivery

Wrong scope. Only the mock call was verified; SMTP/provider/mailbox evidence is needed at higher layers.

### 50.2. Using Real SMTP Accounts in Unit Tests

Unnecessary, flaky, and risks misdirected sends. Use mocks in unit tests and dedicated test servers for transport.

### 50.3. Using Only `any(SimpleMailMessage.class)`

Misses wrong recipients, subjects, and bodies. Use captors and assert key fields.

### 50.4. Policy Mock Defaults to False When `thenReturn(true)` Is Forgotten

Service skips sending and `verify` fails. Configure fixtures for the intended branch.

### 50.5. `createMimeMessage()` Returns Null

Mockito mocks do not build real MIME objects. Stub the factory with a `Session` and `new MimeMessage`.

### 50.6. Mocking Both MimeMessageHelper and MimeMessage

Proves only method calls, not real multipart layout or encoding. Use real MIME objects in composition tests.

### 50.7. Asserting `multipart/*` and Assuming HTML Is Valid

Multipart might hold only an attachment. Inspect `text/plain`, `text/html`, and their decoded content.

### 50.8. Relying on Fixed Part Indexes

MIME can be nested. Walk parts recursively by disposition and MIME type.

### 50.9. Calling `verifyNoInteractions` After a Verified Call

It requires zero interactions of any kind, which fails after the sender was called. Use `verifyNoMoreInteractions` when asserting no extra calls occurred.

### 50.10. Confusing `send(MimeMessage)` and `send(SimpleMailMessage)` Overloads

Stubbing/verifying the wrong signature breaks tests. Match the exact message type.

### 50.11. Treating Batch Tests as an Exactly-Once Guarantee

Unit `times(1)` proves nothing across crashes or partial recipient failures.

### 50.12. MimeMessagePreparator Callback Never Executed

Mocks just receive the callback; use `doAnswer` to run the preparator on a real MIME object when testing content.

### 50.13. Adding `@SpringBootTest` and Assuming Real Network I/O

If the sender bean is mocked, zero SMTP I/O occurs.

### 50.14. Automatically Retrying Every MailException

Permanent, auth, and unknown outcomes need distinct policies. Test the failure classifier at the adapter layer.

### 50.15. Asserting `DELIVERED` Right After `sender.send()`

Even a real sender returning normally proves only submission acceptance. Delivery is observed downstream.

### 50.16. Removing or Bypassing Suppressions to Make Tests Send

Never weaken production business rules to force delivery; use authorized fixtures in tests.

### 50.17. Sending Test Mail to Strangers

Unnecessary. Use `.test` fixtures, mocks, and authorized seed mailboxes when measuring placement.

### 50.18. Using Real Customer Data in Unit Tests

Creates privacy exposure, especially when CI logs failed assertions. Use synthetic data.

### 50.19. Using Arbitrary Sleeps for Async Tests

Prone to flakiness. Use proper synchronization/status checks with timeouts at the right layer.

### 50.20. Reading Mutated Objects from Captors After Invocation

When mutable messages are reused, snapshot inside `doAnswer`.

### 50.21. Disabling Mockito Strict Stubs Globally

Hides broken fixtures. Stub exact branches; use `lenient` only intentionally and narrowly.

### 50.22. Writing Tests Just for Coverage Without Asserting Behavior

Calling a service without verifying outputs, calls, or exceptions protects nothing. Assert against acceptance criteria.

### 50.23. Tests Breaking on Harmless Refactors

Avoid asserting unimportant implementation details. Focus on message outputs and business guards.

### 50.24. Conflating Test-Only Success with Provider Delivery Status

Mocks must never fabricate production delivery evidence. Keep logs and status names accurate to their source.

## 51. Self-Guided Exercise 1: Adding a Business Message-ID Header

Requirement: each message carries a business correlation ID for traceability.

### Approach

With `MimeMessage`, you can set a custom header:

~~~java
mime.setHeader("X-Notification-ID", notificationId);
~~~

This header carries a **business reference**, not an authentication mechanism. Never place secret tokens or directly identifiable personal data in headers. `SimpleMailMessage` lacks an API for arbitrary custom headers; switch to `MimeMessage` when needed.

### Tests to Write

1. Mock `JavaMailSender` with Mockito.
2. Stub `createMimeMessage()` to return a real Jakarta Mail MIME object.
3. Call the service with a test `notificationId`.
4. Capture the `MimeMessage`.
5. Assert:

~~~java
assertEquals(
        "notif-184",
        actual.getHeader("X-Notification-ID", null));
~~~

6. Verify the sender was invoked once.

### Do Not Overclaim

Creating a custom header does not guarantee providers preserve it, recipient servers honor it, or mailboxes deduplicate on it.

## 52. Self-Guided Exercise 2: Inline Resources in HTML

Requirement: the HTML body references a logo via `Content-ID` rather than loading it from an external URL.

HTML snippet:

~~~html
<html>
  <body>
    <img src="cid:brand-logo" alt="Brand logo">
    <p>Your receipt is ready.</p>
  </body>
</html>
~~~

Using `MimeMessageHelper`:

~~~java
helper.setText(plainText, htmlText);
helper.addInline(
        "brand-logo",
        new ByteArrayResource(validPngBytes),
        "image/png");
~~~

In practice, `validPngBytes` must come from a **valid PNG fixture**. Never pass a few text bytes labeled `image/png`, because the MIME type will mismatch the content.

### Checks to Test

- A `text/html` body part contains `cid:brand-logo`.
- A MIME part carries the matching `Content-ID`.
- `Content-Type` matches the image format.
- The inline part is not mistaken for a required downloadable attachment.
- The mock sender receives the MIME message with zero SMTP I/O.

### Note on MIME Nesting

When combining inline resources and attachments, the helper may create `multipart/mixed` containing nested `multipart/related` and `multipart/alternative`. Use a recursive helper rather than assuming parts sit at the root.

### Mocks Do Not Verify Email Client Rendering

Valid MIME does not guarantee every email client renders identically. If visual rendering matters, run separate preview/mail-client checks with valid test data.

## 53. Self-Guided Exercise 3: Ensuring One Notification Does Not Duplicate Within One Execution

Requirement: if the service receives the same business event twice **within one transaction/test context**, the business layer creates only one outbox entry.

Design approach:

~~~text
businessKey = orderId + notificationCategory
outboxRepository.insertIfAbsent(businessKey, payloadRef)
~~~

### Unit Test

Mock the repository so the first insert succeeds and the second sees a duplicate. Assert:

- The service returns the same notification ID or follows clear duplicate rules.
- No extra sender attempt occurs inside the business transaction.
- Two distinct logical records are never written for the same business key.

### Integration Test Required for Concurrency Guarantees

The database needs a unique constraint or atomic upsert. Mockito `verify(repository, times(1))` in a single execution cannot prove two concurrent HTTP requests won't create duplicates. To prove concurrency safety, run integration tests against a real database with matching transaction boundaries.

## 54. Self-Guided Exercise 4: Sender Failure Must Never Become DELIVERED

Suppose a notification worker defines statuses:

~~~text
PENDING
PROCESSING
SUBMITTED
RETRY_PENDING
FAILED_PERMANENT
SUBMISSION_UNKNOWN
~~~

Requirements:

1. When a message is invalid, never call the sender.
2. When `send()` throws an error classified as temporary, schedule a retry if budget remains.
3. When the error is permanent, record terminal failure.
4. When the transport outcome is uncertain, never resend automatically.
5. When `send()` returns normally, record `SUBMITTED` rather than `DELIVERED`.

### Testing with Mockito

~~~text
Given: sender mock, repository mock, normalized error policy
When:  dispatcher sends valid message
Then:  verify sender invoked
       verify recordSubmissionAccepted()
       never recordDelivered()
~~~

`recordSubmissionAccepted()` and `recordDelivered()` are illustrative domain repository method names, not Spring Mail APIs. Define your own interfaces and add unit tests for the worker.

### What Mocks Do Not Prove

No real SMTP call happens; exception-to-category mapping and relay behavior need separate integration tests. A mocked sender returning normally is a **simulated transport success**, not real provider acceptance.

## 55. Extended Exercise: Testing Multiple Recipients and Privacy

Requirement: an email is sent to `To` along with `Cc` and `Bcc`, while `Bcc` recipients never appear in the subject or body.

### Writing the Test

- Capture `SimpleMailMessage` to assert `getTo()`, `getCc()`, and `getBcc()`.
- Assert neither text nor subject exposes hidden email addresses.
- For MIME, assert proper headers without manually injecting invalid `Bcc:` headers.
- To prove actual **envelope recipients**, use a local SMTP server that exposes `RCPT TO`.

### An Often-Overlooked Point

When sending to multiple recipients, provider outcomes can differ per recipient. Mocks cannot model partial acceptance, so critical systems should track per-recipient delivery states and test the adapter accordingly.

## 56. Sample Scenarios for Self-Verification

### Scenario A: Valid Receipt

**Given**

~~~text
recipient = buyer@example.test
orderId = order-184
policy = ALLOWED
~~~

**When** `sendReceipt(...)` is called.

**Then:**

~~~text
mock send invocations = 1
From = billing@example.test
Reply-To = support@example.test
To = buyer@example.test
Subject = Receipt for order order-184
Body = Your order order-184 has been recorded.
~~~

Zero SMTP network traffic.

### Scenario B: Policy Rejects

**Given** `policy.canReceiveTransactionalMail(...)` returns false.

**Then** `verifyNoInteractions(mailSender)`.

### Scenario C: Blank Recipient

**Given** recipient is a whitespace string.

**Then** `IllegalArgumentException`, without calling policy or sender.

### Scenario D: Simulated Sender Failure

**Given** Mockito `doThrow(new MailSendException(...))`.

**Then** the service throws per its contract and never reports delivered.

### Scenario E: MIME HTML + Attachment

**Given** fixture `order-184`.

**Then:**

~~~text
MIME Subject = Receipt for order order-184
To = buyer@example.test
text/plain contains order-184
text/html contains order-184
attachment name = receipt.txt
attachment bytes = UTF-8("Receipt: order-184")
~~~

Inspected via a Jakarta Mail MIME parser while `JavaMailSender` stays mocked.

## 57. Practice Project Completion Criteria

After building the project and running tests, review this checklist:

### Project and Dependencies

- [ ] Java version matches the chosen Spring Boot / Spring Framework version.
- [ ] Spring Mail starter included.
- [ ] JUnit Jupiter / Mockito JUnit Jupiter included.
- [ ] Unit tests require no SMTP host or password.
- [ ] No real mailboxes or accounts used in fixtures.

### SimpleMailMessage

- [ ] Service uses constructor-injected `JavaMailSender`.
- [ ] Separate `RecipientPolicy` defined.
- [ ] Valid recipient and order ID tested.
- [ ] `From`, `Reply-To`, `To`, subject, and body asserted via `ArgumentCaptor`.
- [ ] `send()` verified to be called once on the valid branch.
- [ ] Rejected policy branch verified not to call sender.
- [ ] Blank input verified not to call sender.
- [ ] `MailSendException` handling tested per contract.

### MimeMessage

- [ ] Service builds both plain-text and HTML alternatives.
- [ ] Mock `createMimeMessage()` stubbed to return a real Jakarta Mail MIME object.
- [ ] `send(MimeMessage)` tested and captured.
- [ ] Headers, UTF-8, and MIME structure asserted.
- [ ] Nested multiparts walked recursively instead of assuming fixed part indexes.
- [ ] Attachment filename and bytes tested.
- [ ] No unescaped user data injected into HTML.

### Scope of Evidence

- [ ] Unit test names make no unfounded `DELIVERED` claims.
- [ ] Unit mocks are never used to claim SMTP connectivity or Inbox placement.
- [ ] Local SMTP integration suite planned when transport testing is needed.
- [ ] `SUBMITTED` and `DELIVERED` separated in production models.
- [ ] `SUBMISSION_UNKNOWN` and already-accepted sends never retried blindly.

This checklist guides hands-on practice. It **does not assert** that the reader's project has been executed or that every test in this article has been run against a specific application.

## 58. Self-Check Questions

**1. Why mock JavaMailSender in unit tests?**

To verify message fields, business guards, and transport-boundary invocations quickly and deterministically without opening SMTP sockets.

**2. When Mockito verifies `send()` succeeded, what is proven?**

That one call with matching arguments occurred on the mock during that test execution; it does not prove external delivery.

**3. What is ArgumentCaptor used for?**

Capturing the message object passed to the mock so you can assert `To`, `From`, `Reply-To`, subject, body, or MIME structure.

**4. What is the difference between `verifyNoInteractions` and `verifyNoMoreInteractions`?**

`verifyNoInteractions` requires the mock was never called at all; `verifyNoMoreInteractions` requires no unverified calls remain.

**5. What does an unstubbed Mockito boolean method normally return?**

Normally `false`, which can cause a service to take the non-sending branch.

**6. Why use `doThrow` for `send()`?**

Because `send()` returns `void`, Mockito requires the `doThrow(...).when(mock).send(...)` syntax.

**7. Why might a mocked `createMimeMessage()` return null?**

Because Mockito does not construct real `MimeMessage` instances automatically; you must stub the factory for MIME tests.

**8. How do you create a real MimeMessage without connecting to SMTP?**

Use `new MimeMessage(Session.getInstance(new Properties()))` in tests.

**9. Why shouldn't you mock MimeMessage itself?**

To inspect real MIME headers, encoding, multiparts, and decoded content, you need a real MIME object that can be inspected and serialized.

**10. What does `MimeMessageHelper.setText(plain, html)` create?**

Two versions of the content—plain text and HTML—typically organized as a multipart alternative inside the MIME tree.

**11. Why traverse MIME parts recursively?**

Multiparts can nest `mixed`, `related`, and `alternative`; HTML is not guaranteed to sit at a fixed index.

**12. Is testing the attachment name enough to prove the bytes are right?**

No. You must locate the attachment part and compare its stream bytes against the fixture.

**13. When testing Unicode content, should you assert raw encoded header text or decoded content?**

Depends on the goal; to verify reader-visible text, prefer decoded subject/body. Wire header encoding requires separate dedicated tests.

**14. When using `MimeMessagePreparator`, does a mock run the callback automatically?**

No. Use `doAnswer` to invoke the preparator on a real MIME object when testing content.

**15. Does `@SpringBootTest` automatically create an SMTP integration test?**

No. If `JavaMailSender` is mocked, no network transport happens.

**16. Do unit tests need `spring.mail.password`?**

No. Mockito mocks do not connect to SMTP; never place secrets in test code.

**17. Can you test SPF/DKIM/DMARC with Mockito?**

No. That requires DNS/authentication checks and receiving messages over an authorized real mail path.

**18. Does testing a send to one recipient prove an entire batch was delivered?**

No. Recipients can be accepted, rejected, or bounced individually.

**19. Why does a `times(1)` invocation not guarantee exactly-once across crashes?**

Production workers can redeliver a job after SMTP accepted the message but before the DB recorded the outcome.

**20. When an SMTP provider accepts a message, what status should the application record?**

Typically `SUBMITTED` or `ACCEPTED` with clear meaning; `DELIVERED` requires downstream delivery evidence.

**21. Why might an exception not mean the email was never sent?**

Losing the final reply after `DATA` leaves the application unsure whether the relay accepted the message.

**22. Should you retry immediately whenever the mock sender throws MailSendException?**

There is no one-size-fits-all rule. Classify error, phase, budget, and duplicate risk; mock exceptions merely simulate failures.

**23. Why avoid real SMTP accounts in CI unit tests?**

They introduce network/secret dependencies, flaky tests, and accidental sends.

**24. If a service calls `send(MimeMessage)`, is verifying `send(SimpleMailMessage)` valid?**

No. Those are different overloads; matchers must match the exact type.

**25. When testing callbacks, does `verify(send(any(Preparator.class)))` prove headers are right?**

No. Tests must execute the preparator on a real MIME object and inspect its contents.

**26. Does a captor automatically snapshot a message at invocation time?**

No; it normally holds the reference. If the mutable object is modified afterward, snapshot inside `doAnswer` as needed.

**27. To prove the SMTP client actually sends wire data, which test should you use?**

Use local/scripted SMTP integration tests with a real `JavaMailSenderImpl` and a test relay.

**28. Does a local SMTP server receiving an email prove it reaches a Gmail Inbox?**

No. It proves only that the test relay accepted the submission.

**29. To evaluate Inbox placement, what sources are required?**

Authorized seed mailboxes or a clearly defined placement measurement setup, along with provider events and appropriate sample/time windows.

**30. If a recipient is blocked by policy, what is the key assertion?**

Zero send calls on `JavaMailSender`, confirming the policy branch took effect.

**31. For an expired OTP, how many calls should the mock sender receive?**

Zero calls if the expiration guard works and the request is no longer eligible.

**32. Should a test that only verifies the sender be named `emailDeliveredSuccessfully`?**

No. Name it after the observed behavior: `createsExpectedMessageAndInvokesSender`.

## Conclusion

**Testing messages with a mock `JavaMailSender` is a foundational skill in Spring Framework Mail practice projects.** Used properly, Mockito verifies recipients, `From`, `Reply-To`, subjects, bodies, send-suppression policies, call counts, and error handling without an SMTP server or Internet access. For `SimpleMailMessage`, use `ArgumentCaptor` to inspect fields. For HTML and attachments, create a real `MimeMessage` via Jakarta Mail, mock `createMimeMessage()` and `send()`, and walk the MIME tree to inspect content and bytes.

However, **a green test is only meaningful within the scope it actually observes**. `verify(sender).send(...)` proves neither SMTP acceptance, provider delivery, Inbox placement, nor user reads. Name tests accurately, keep unit, MIME, integration, and provider layers distinct, never mark `DELIVERED` just because a mock threw no error, and add SMTP integration and observability when requirements extend beyond message composition.

With these patterns, you can write unit test suites that are **fast, explicit, safe, and CI-friendly**, while knowing exactly when to step beyond Mockito to verify transport and deliverability in controlled environments.
