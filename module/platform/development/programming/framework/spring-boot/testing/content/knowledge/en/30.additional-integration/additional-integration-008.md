# Testing Email with a Mock Mail Server: Verifying Recipients, Content, and MIME Messages in Spring Boot Test

## 1. The problem: testing real SMTP sending without sending mail to the Internet

A Spring Boot application frequently sends registration confirmations, password resets, order notifications, or reports with attachments. If a unit test only asserts `verify(javaMailSender).send(...)`, we know a Java method was invoked, yet **we still do not know what SMTP transport actually sent**: recipient addresses, accented Unicode subjects, HTML body contents, whether Cc/Bcc recipients received copies, or whether attachments arrived intact.

Conversely, you should never use Gmail accounts, corporate SMTP servers, or real customer addresses in CI. Sending live emails during test runs risks data leaks, spam, cost, rate limits, and network-dependent flakiness.

This lesson's solution: run an **in-memory mock SMTP server on `127.0.0.1` with a dynamic port** using GreenMail. Let Spring Boot's real `JavaMailSender` connect to that server over SMTP; GreenMail stores incoming mail in sandbox mailboxes, and JUnit reads those received messages to verify **envelope recipients**, **To/Cc**, **From**, **Subject**, **plain-text/HTML MIME parts**, **attachments**, **UTF-8**, and **send counts**. No external SMTP provider is used.

~~~text
Spring Boot ApplicationContext
     |
     | NotificationMailer
     | (SimpleMailMessage / MimeMessageHelper)
     v
JavaMailSender (Spring Boot mail auto-configuration)
     |
     | SMTP TCP to 127.0.0.1:<dynamic-port>
     v
GreenMail embedded SMTP server (test-only)
     |
     +--> mailbox alice@sample.test
     +--> mailbox manager@sample.test
     +--> mailbox audit@sample.test (Bcc)
              |
              v
       JUnit verifies content and recipient delivery
~~~

**Learning objectives:**
1. Understand `JavaMailSender`, `SimpleMailMessage`, `MimeMessageHelper`, Jakarta Mail, and Spring Boot mail auto-configuration.
2. Distinguish a **mocked `JavaMailSender` unit test** from a **mock SMTP server integration test**: two layers verifying different contracts.
3. Configure **GreenMail 2.1.x** compatible with **Spring Boot 3.3.5 / Java 17** Jakarta Mail; avoid GreenMail 1.6 / legacy `javax.mail` with `jakarta.mail` code.
4. Start the SMTP sandbox on **port 0 / dynamic port** and inject `spring.mail.port` via `@DynamicPropertySource` before Spring builds the `ApplicationContext`.
5. Send plain-text email with `SimpleMailMessage` and verify **exact recipient, sender address, subject, and UTF-8 body**.
6. Send to multiple **To, Cc, and Bcc** recipients and verify **the Bcc mailbox actually receives the message** rather than confusing MIME Bcc headers with SMTP envelope recipients.
7. Build **multipart/alternative + attachment** emails with `MimeMessageHelper` and traverse nested MIME parts properly instead of casting `MimeMessage.getContent()` directly to `String`.
8. Assert **0/1/2 emails** and confirm no messages leak into unintended mailboxes.
9. Add negative tests: disabled notifications, invalid recipients, subjects containing CR/LF, and invalid inputs **send zero SMTP messages**.
10. Explain the scope boundary: GreenMail proves the app handed messages to a sandbox SMTP server—it **does not** prove delivery to Gmail/Outlook inboxes, SPF/DKIM/DMARC, or external deliverability.
11. Cover how to test SMTP errors, timeouts, retries/idempotency, async email, and sensitive production data.
12. Run a standalone Gradle project containing **15 JUnit Jupiter `@Test` methods** with no Docker and no network access outside localhost.

**Parent context ("Additional integration"):** This lesson covers **email integration testing**. It does not replace an entire Notification/Marketing module, nor does it set up real login or HTTP servers. The key takeaway is distinguishing SMTP-boundary evidence from mere mock invocation counts.

**Example versions:** Java 17, Spring Boot **3.3.5**, Spring Framework 6.1 / Spring Mail, Jakarta Mail 2.x, GreenMail **2.1.14**, Gradle, and JUnit Jupiter. GreenMail 2.1.x uses **`jakarta.mail.*`** and version 2.1.14 is available on Maven Central. When upgrading Spring Boot or GreenMail, verify actual version APIs and dependencies; never mix `javax.mail.internet.MimeMessage` with `jakarta.mail.internet.MimeMessage`.

## 2. Clear definitions: send, accept, deliver, and receive are distinct milestones

| Milestone | Where observed? | Proven by this test? |
|---|---|---|
| Service calls `JavaMailSender.send(...)` | Mockito verify or code path | **Yes**, though not SMTP delivery |
| Jakarta Mail builds valid MIME | MIME parts/headers on mock server | **Yes** |
| Client opens TCP/SMTP to server | GreenMail receives and stores message | **Yes**, for localhost sandbox |
| SMTP envelope `RCPT TO` is right | GreenMail mailbox for each recipient | **Yes**, including Bcc |
| Mock server accepted SMTP `DATA` | Message appears in GreenMail mailbox | **Yes** |
| Corporate mail server accepted it | Integration with real provider | **No** |
| DNS MX, SPF, DKIM, DMARC valid | DNS/provider/specialized tools | **No** |
| Email reaches external Internet inbox | Provider/webhook/seed inbox | **No** |
| Recipient opens email, links work | Email tracking and functional E2E | **No** |

In SMTP, outbound email consists of an **envelope** (`MAIL FROM`, `RCPT TO`) and a **MIME message** (headers/body). They are related but distinct:

~~~text
Envelope:
  MAIL FROM:<no-reply@sample.test>
  RCPT TO:<alice@sample.test>
  RCPT TO:<manager@sample.test>
  RCPT TO:<audit@sample.test>

MIME headers/body:
  From: no-reply@sample.test
  To: alice@sample.test
  Cc: manager@sample.test
  Subject: Báo cáo tháng 11
  MIME-Version: 1.0
  Content-Type: multipart/mixed; ...

  (multipart/alternative plain+html)
  (attachment summary.txt)
~~~

**Bcc has special semantics:** a Bcc recipient still receives an **SMTP `RCPT TO`** so its mailbox gets the mail, yet **Bcc should not appear in headers of copies delivered to other recipients**. Consequently, a test calling `mimeMessage.getRecipients(Message.RecipientType.BCC)` may get `null` even when Bcc succeeded. The runnable example checks **the Bcc mailbox in GreenMail**, without forcing implementation-specific assumptions about Bcc headers.

**Never treat SMTP `250 OK` as proof of inbox delivery**: real providers enforce spam filters, sender reputation, bounces, delayed queues, routing, and domain policies. GreenMail intentionally serves as a sandbox to verify application-side contracts without sending outside traffic.

## 3. Choosing tools: mock `JavaMailSender`, GreenMail, or Mailpit/MailHog?

| Approach | Real SMTP TCP? | Verifies | Cannot verify |
|---|---|---|---|
| Mockito `@MockBean JavaMailSender` | **No** | Send call count, objects built before sending | Final MIME serialization, SMTP connection, mailbox delivery |
| **Embedded GreenMail** | **Yes, over localhost** | `JavaMailSender` auto-config, SMTP send, MIME, To/Cc/Bcc delivery, attachments | Internet deliverability, full provider auth/TLS policies |
| Mailpit / MailHog (container/standalone) | Yes | SMTP sandbox, web UI/API inspection, CI E2E | Real inbox deliverability |
| SMTP provider sandbox API | Yes, to provider test env | Some provider/policy integration | Not equivalent to real user inboxes |
| Sending via production SMTP | Yes | Only narrow smoke tests with strict guardrails | Misdelivery risk, cost/rate limits, flakiness |

**Why not Mockito alone?** A test like:

~~~java
verify(mailSender, times(1)).send(any(MimeMessage.class));
~~~

can pass even if To/Cc/Bcc addresses are wrong, the HTML body holds stale content, or attachment bytes are missing. Nor does it verify whether Spring Boot configured `spring.mail.host` and `spring.mail.port` properly.

**Why no Docker needed?** GreenMail runs **embedded inside the same JVM**. SMTP still runs over a real loopback socket, without container runtimes, image pulls, or external SMTP credentials. It is ideal for fast mail integration tests. When pipelines need a separate mail server process or container, Mailpit, MailHog, or standalone GreenMail remains valuable.

**Why distinguish a mock server from a fake `JavaMailSender`?** A fake `JavaMailSender` may simply record `MimeMessage` objects in memory, skipping serialization and network transmission. GreenMail communicates over SMTP at a deeper integration boundary where encoding, payload, and port config bugs surface.

## 4. Spring Boot Mail auto-configuration

Add the dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
~~~

Spring Boot auto-configures a `JavaMailSenderImpl` when the mail libraries are present and `spring.mail.host` is configured (unless the app defines its own sender bean). Common properties:

| Property | Meaning |
|---|---|
| `spring.mail.host` | SMTP host; the test uses **127.0.0.1** |
| `spring.mail.port` | SMTP port; the test uses **GreenMail's dynamic port** |
| `spring.mail.username`, `spring.mail.password` | SMTP auth credentials when required; omitted in default GreenMail test |
| `spring.mail.protocol` | Typically `smtp` |
| `spring.mail.default-encoding` | Default UTF-8 encoding for MIME messages when configured |
| `spring.mail.properties[mail.smtp.auth]` | Enables/disables SMTP AUTH |
| `spring.mail.properties[mail.smtp.starttls.enable]` | Enables/disables STARTTLS in JavaMail |
| `spring.mail.properties[mail.smtp.connectiontimeout]` | Connection timeout in milliseconds |
| `spring.mail.properties[mail.smtp.timeout]` | Read timeout |
| `spring.mail.properties[mail.smtp.writetimeout]` | Write timeout |

**Critical note:** JavaMail defaults some timeouts to infinite if left unset. Tests should configure finite timeouts so SMTP stalls do not hang CI. The 3000 ms values in this lesson fit loopback traffic; production must account for SLOs, retries, and provider limits.

**STARTTLS and SMTP AUTH:** the GreenMail server in this example **disables auth/TLS** to focus on content and recipients; that **does not mean disabling STARTTLS/auth in production**. Testing STARTTLS/SMTPS, certificate trust, and credentials belongs to a separate integration suite with explicit SSL/auth server settings.

**Avoid hardcoding port 3025:** `ServerSetupTest.SMTP` has a default test port, yet parallel tests or Windows reserved port ranges cause collisions. `ServerSetupTest.SMTP.dynamicPort()` lets the server bind a free port. Tests read `GREEN_MAIL.getSmtp().getPort()` after startup to supply it to the Spring Environment.

### 4.1. `@DynamicPropertySource` solves bootstrap ordering

With `@SpringBootTest`, the `ApplicationContext` needs the SMTP host and port **before instantiating `JavaMailSender`**. Because GreenMail selects its port at startup, use:

~~~java
@DynamicPropertySource
static void smtpProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.mail.port",
            () -> GREEN_MAIL.getSmtp().getPort());
}
~~~

This snippet sits in a **test class where `static GreenMail GREEN_MAIL` has already started**, not a standalone file. Spring Test registers the dynamic property supplier during context setup, avoiding edits to production `application.yml` or hardcoded ports.

**Do not wait until `@BeforeEach` to change `spring.mail.port`:** by then, the `ApplicationContext` and sender bean already exist. In the runnable example, GreenMail starts in a static initializer **before** the dynamic property supplier runs, so the port is already bound. `@AfterAll` stops the server once when the test class finishes.

**`ApplicationContext` caching caveat:** if multiple test classes reuse one cached Spring context whose mail sender points at a stopped GreenMail port, later classes suffer connection refused errors. Across multiple classes, use explicit shared lifecycle/config caching, selective `@DirtiesContext`, or isolated contexts per class. The sample project uses **a single Spring Boot integration test class** to keep lifecycles aligned.

## 5. Email concepts to verify

### 5.1. Plain email vs. multipart MIME

**Plain:** `SimpleMailMessage` holds `from`, `to`, `cc`, `bcc`, `subject`, and `text`. Suitable for plain-text emails without attachments; it cannot represent HTML/multipart structures or binary attachments.

**MIME:** `JavaMailSender.createMimeMessage()` and Spring's `MimeMessageHelper` build `jakarta.mail.internet.MimeMessage`. They support:
- `multipart/alternative` containing **text/plain** and **text/html**.
- `multipart/mixed` wrapping multiple MIME parts, such as an alternative body and attachments.
- Attachments with `Content-Disposition: attachment` and filenames.
- UTF-8 subjects/bodies, encoded headers, and Content-Type/charset parameters.

**Avoid comparing raw MIME strings verbatim** unless required by contract: JavaMail generates MIME boundaries, `Message-ID`, transfer encodings (Base64/quoted-printable), `Date`, and header ordering dynamically. Raw-string tests break easily after library updates. Parse the `MimeMessage` and assert **decoded content** and **recipient lists**.

### 5.2. To/Cc/Bcc behave differently

- **To**: primary recipients, normally visible in headers.
- **Cc**: publicly copied recipients; addresses appear in headers.
- **Bcc**: blind-copied recipients; SMTP delivery still routes to Bcc recipients, yet other recipients must not see the Bcc list in their received message headers.
- **Envelope recipient**: SMTP `RCPT TO` used by the server to route mail—more reliable evidence than inspecting an implementation-dependent Bcc header.

**Mock SMTP tests must verify both angles:** `To`/`Cc` headers for visible recipients, plus **each intended mailbox** receiving exactly one copy. Asserting only `greenMail.getReceivedMessages().length == 3` without checking who received them misses misrouted emails. Use `GreenMail.findReceivedMessages(userPredicate,messagePredicate)` to query **per-address mailboxes**.

### 5.3. Accented and Unicode content

Test with accented non-ASCII strings such as `"Xác nhận đơn #42"`, `"Xin chào, đơn hàng đã được ghi nhận."`, and `"Báo cáo tháng 11"`. Never test solely with ASCII `"hello"`; charset, encoded-subject, and MIME-decoding bugs only appear with Unicode.

In tests, `MimeMessage.getSubject()` returns the **decoded string** when Jakarta Mail parses the encoding; for text MIME parts, `Part.getContent()` returns decoded text per charset. On multi-line bodies, SMTP may canonicalize line endings to CRLF; assert **semantic text** or normalize line endings per contract rather than comparing raw MIME bytes.

### 5.4. Attachments

Verify at least:
- Presence of a MIME part with `Content-Disposition: attachment`.
- `getFileName()` matches expected filename, e.g. `summary.txt`.
- Bytes read via `getInputStream().readAllBytes()` **match fixture bytes identically**.
- Appropriate `Content-Type` if specified by contract.
- Attachments do not leak into `text/plain` body content when traversing nested MIME parts.

**Never stop at `message.isMimeType("multipart/*")`:** that does not prove the attachment has the right filename or bytes. HTML, plain text, and attachments can sit at different nesting levels, requiring recursive traversal.

## 6. Runnable project: Spring Boot 3.3.5 + GreenMail 2.1.14

### 6.1. Directory layout

~~~text
settings.gradle
build.gradle
src/main/java/demo/mail/MailDemoApplication.java
src/main/java/demo/mail/NotificationMailer.java
src/test/java/demo/mail/NotificationMailerSmtpTest.java
~~~

No `application.properties` is needed because the test class supplies SMTP host, timeouts, and sender config, while `@DynamicPropertySource` supplies the port. Neither an HTTP controller nor a real database is required.

**settings.gradle**

~~~groovy
rootProject.name = 'spring-mail-greenmail-contract-tests'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.icegreen:greenmail:2.1.14'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Why use `com.icegreen:greenmail` instead of `greenmail-junit5`?** The example manages `GreenMail.start()/stop()` explicitly in one class to **guarantee SMTP is already listening before Spring Boot reads the dynamic port**. GreenMail offers `greenmail-junit5`/`GreenMailExtension`, yet combining JUnit extensions with Spring context bootstrap ordering and caching requires careful coordination. Using the **core library** alongside `starter-test`'s JUnit Jupiter avoids two lifecycle managers competing over one server.

**Compatibility:** GreenMail 2.1.14 targets Jakarta Mail 2.1.x, matching Spring Boot 3.3.x's `jakarta.mail.*` imports. Do not use GreenMail 1.6 (`javax.mail`) here. Gradle/Maven still need repository access on the first run unless dependencies are cached; mock SMTP itself needs no Internet access.

### 6.2. Application class

**src/main/java/demo/mail/MailDemoApplication.java**

~~~java
package demo.mail;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MailDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MailDemoApplication.class, args);
    }
}
~~~

The app does not include `spring-boot-starter-web`, so the Spring Boot context starts without an HTTP server. Mail is sent by the Spring-managed service via the auto-configured `JavaMailSender`.

### 6.3. Mail service with validation and MIME support

**src/main/java/demo/mail/NotificationMailer.java**

~~~java
package demo.mail;

import java.nio.charset.StandardCharsets;
import java.util.Objects;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailer {

    private final JavaMailSender sender;
    private final String from;

    public NotificationMailer(
            JavaMailSender sender,
            @Value("${app.mail.from:no-reply@sample.test}")
            String from) {
        this.sender = sender;
        this.from = from;
    }

    private static void requireAddress(String email) {
        if (email == null || email.isBlank()
                || email.indexOf('\r') >= 0
                || email.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(
                    "A mailbox address is required");
        }

        try {
            InternetAddress address = new InternetAddress(email, true);
            address.validate();

            if (!email.equals(address.getAddress())
                    || !email.contains("@")) {
                throw new IllegalArgumentException(
                        "Only a single mailbox address is allowed");
            }
        } catch (AddressException ex) {
            throw new IllegalArgumentException(
                    "Invalid mailbox address", ex);
        }
    }

    private static void requireSubject(String subject) {
        if (subject == null || subject.isBlank()
                || subject.indexOf('\r') >= 0
                || subject.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(
                    "Subject must be nonblank and single-line");
        }
    }

    public void sendPlain(
            String to, String subject, String body) {

        requireAddress(to);
        requireSubject(subject);
        Objects.requireNonNull(body, "body");

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject(subject);
        message.setText(body);

        sender.send(message);
    }

    public boolean sendIfEnabled(
            boolean enabled,
            String to,
            String subject,
            String body) {

        if (!enabled) {
            return false;
        }

        sendPlain(to, subject, body);
        return true;
    }

    public void sendSummary(
            String to,
            String cc,
            String bcc,
            String subject,
            String plainText,
            String htmlText,
            byte[] attachment) {

        requireAddress(to);
        if (cc != null && !cc.isBlank()) {
            requireAddress(cc);
        }
        if (bcc != null && !bcc.isBlank()) {
            requireAddress(bcc);
        }
        requireSubject(subject);
        Objects.requireNonNull(plainText, "plainText");
        Objects.requireNonNull(htmlText, "htmlText");
        Objects.requireNonNull(attachment, "attachment");

        MimeMessage message = sender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message, true, StandardCharsets.UTF_8.name());

            helper.setFrom(from);
            helper.setTo(to);

            if (cc != null && !cc.isBlank()) {
                helper.setCc(cc);
            }
            if (bcc != null && !bcc.isBlank()) {
                helper.setBcc(bcc);
            }

            helper.setSubject(subject);
            // Multipart alternative: text/plain and text/html.
            helper.setText(plainText, htmlText);

            // Multipart mixed: file attached independently of body.
            helper.addAttachment(
                    "summary.txt",
                    new ByteArrayResource(attachment),
                    "text/plain; charset=UTF-8");

            sender.send(message);
        } catch (MessagingException ex) {
            throw new MailPreparationException(
                    "Could not prepare MIME email", ex);
        }
    }
}
~~~

**Design choices explained:**

- **Injected `JavaMailSender`**: uses Spring Boot's implementation configured via `spring.mail.*` instead of instantiating `new Session(...)` or `new JavaMailSenderImpl()` inside the service, exercising a production-like SMTP path.
- **Fixed `From` via `app.mail.from`**: prevents callers from spoofing sender identities arbitrarily. Tests use the `.test` domain.
- **Address validation**: strict `InternetAddress` parsing and `.validate()` catch syntax and CRLF issues. Checking `email.equals(address.getAddress())` rejects display-name wrappers or multi-address lists on single-mailbox APIs. This is **basic syntax validation** only—it does not verify MX records or mailbox ownership.
- **No CR/LF in subjects**: mitigates header injection. The policy permits Unicode while forbidding multi-line strings carrying forged headers.
- **`sendPlain`**: uses `SimpleMailMessage` when only plain text is needed.
- **`sendIfEnabled`**: business branch for **zero-send** tests. Returns `false` when disabled, producing zero SMTP side effects.
- **`sendSummary`**: uses `MimeMessageHelper(..., true, "UTF-8")` for multipart MIME; `.setText(plain, html)` creates both representations; the attachment carries raw bytes and an explicit filename.
- **Optional Cc/Bcc**: null or blank means omitted. Any provided address is validated prior to MIME assembly/sending.
- **`MailPreparationException`**: wraps `MessagingException` during message construction, while actual SMTP transport failures in `sender.send(...)` throw `MailException` subtypes. Never catch and swallow exceptions here.
- **Never send to real domains**: `.test` is reserved for testing; addresses exist solely in sandbox mailboxes and never route to the Internet.

**Validation limits:** the demo omits internationalized email canonicalization, IDN/punycode, allowed-domain lists, recipient caps, and risk scoring. If an app sends to arbitrary user-supplied addresses, add strict validation, authorization, business limits, and anti-spam controls. `InternetAddress.validate()` does not confirm an inbox exists; keep syntax checks distinct from real deliverability.

## 7. JUnit SMTP integration class: inspecting mailboxes and parsing MIME

**src/test/java/demo/mail/NotificationMailerSmtpTest.java**

~~~java
package demo.mail;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;

import com.icegreen.greenmail.util.GreenMail;
import com.icegreen.greenmail.util.ServerSetupTest;
import jakarta.mail.Address;
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties = {
        "spring.mail.host=127.0.0.1",
        "spring.mail.protocol=smtp",
        "spring.mail.default-encoding=UTF-8",
        "spring.mail.properties.mail.smtp.auth=false",
        "spring.mail.properties.mail.smtp.starttls.enable=false",
        "spring.mail.properties.mail.smtp.connectiontimeout=3000",
        "spring.mail.properties.mail.smtp.timeout=3000",
        "spring.mail.properties.mail.smtp.writetimeout=3000",
        "app.mail.from=no-reply@sample.test"
})
class NotificationMailerSmtpTest {

    private static final String ALICE = "alice@sample.test";
    private static final String MANAGER = "manager@sample.test";
    private static final String AUDIT = "audit@sample.test";

    // Test-only SMTP server: loopback + random port.
    private static final GreenMail GREEN_MAIL =
            new GreenMail(
                    ServerSetupTest.SMTP.dynamicPort());

    static {
        GREEN_MAIL.start();
    }

    @DynamicPropertySource
    static void smtpPort(DynamicPropertyRegistry properties) {
        properties.add(
                "spring.mail.port",
                () -> GREEN_MAIL.getSmtp().getPort());
    }

    @Autowired
    NotificationMailer mailer;

    @Autowired
    JavaMailSender sender;

    @BeforeEach
    void clearMailboxes() throws Exception {
        GREEN_MAIL.purgeEmailFromAllMailboxes();
    }

    @AfterAll
    static void stopSmtpServer() {
        GREEN_MAIL.stop();
    }

    private long countMail(String mailbox) {
        return GREEN_MAIL.findReceivedMessages(
                user -> mailbox.equalsIgnoreCase(user.getEmail()),
                message -> true
        ).count();
    }

    private MimeMessage singleMail(String mailbox) {
        List<MimeMessage> messages =
                GREEN_MAIL.findReceivedMessages(
                        user -> mailbox.equalsIgnoreCase(
                                user.getEmail()),
                        message -> true
                ).toList();

        assertEquals(
                1, messages.size(),
                "Expected exactly one mail in " + mailbox);

        return messages.get(0);
    }

    private static List<String> mailboxes(Address[] addresses) {
        if (addresses == null) {
            return List.of();
        }
        return Arrays.stream(addresses)
                .map(address ->
                        ((InternetAddress) address).getAddress())
                .toList();
    }

    private static String findTextPart(
            Part part, String expectedMimeType)
            throws Exception {

        if (Part.ATTACHMENT.equalsIgnoreCase(
                part.getDisposition())) {
            return null;
        }

        if (part.isMimeType(expectedMimeType)) {
            return (String) part.getContent();
        }

        if (part.isMimeType("multipart/*")) {
            Multipart multipart = (Multipart) part.getContent();

            for (int i = 0; i < multipart.getCount(); i++) {
                String result = findTextPart(
                        multipart.getBodyPart(i), expectedMimeType);
                if (result != null) {
                    return result;
                }
            }
        }

        return null;
    }

    private static Part findAttachment(
            Part part, String filename)
            throws Exception {

        if (Part.ATTACHMENT.equalsIgnoreCase(
                part.getDisposition())
                && filename.equals(part.getFileName())) {
            return part;
        }

        if (part.isMimeType("multipart/*")) {
            Multipart multipart = (Multipart) part.getContent();

            for (int i = 0; i < multipart.getCount(); i++) {
                Part result = findAttachment(
                        multipart.getBodyPart(i), filename);
                if (result != null) {
                    return result;
                }
            }
        }

        return null;
    }

    @Test
    void plainMailHasToFromSubjectAndUtf8Body()
            throws Exception {

        mailer.sendPlain(
                ALICE,
                "Xác nhận đơn #42",
                "Xin chào, đơn hàng đã được ghi nhận.");

        MimeMessage received = singleMail(ALICE);

        assertEquals(
                List.of(ALICE),
                mailboxes(received.getRecipients(
                        Message.RecipientType.TO)));
        assertEquals(
                List.of("no-reply@sample.test"),
                mailboxes(received.getFrom()));
        assertEquals(
                "Xác nhận đơn #42",
                received.getSubject());
        assertEquals(
                "Xin chào, đơn hàng đã được ghi nhận.",
                ((String) received.getContent()).strip());
        assertTrue(received.isMimeType("text/plain"));
    }

    @Test
    void twoDifferentRecipientsDoNotLeakIntoOtherMailbox() {
        mailer.sendPlain(ALICE, "One", "Message one");
        mailer.sendPlain(MANAGER, "Two", "Message two");

        assertEquals(1L, countMail(ALICE));
        assertEquals(1L, countMail(MANAGER));
        assertEquals(0L, countMail(AUDIT));
        assertEquals(0L, countMail("stranger@sample.test"));
    }

    @Test
    void twoSendsToSameRecipientCreateTwoMessages() {
        mailer.sendPlain(ALICE, "First", "One");
        mailer.sendPlain(ALICE, "Second", "Two");

        assertEquals(2L, countMail(ALICE));
        assertEquals(0L, countMail(MANAGER));
    }

    @Test
    void disabledNotificationDoesNotSendAnyMail() {
        boolean sent = mailer.sendIfEnabled(
                false,
                ALICE,
                "Feature disabled",
                "This must not be sent");

        assertFalse(sent);
        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void enabledNotificationSendsExactlyOneMail()
            throws Exception {

        boolean sent = mailer.sendIfEnabled(
                true,
                ALICE,
                "Đã bật thông báo",
                "Chào bạn!");

        assertTrue(sent);
        assertEquals(1L, countMail(ALICE));
        assertEquals(
                "Đã bật thông báo",
                singleMail(ALICE).getSubject());
    }

    @Test
    void invalidToIsRejectedBeforeSmtp() {
        assertThrows(
                IllegalArgumentException.class,
                () -> mailer.sendPlain(
                        "not-an-email",
                        "Invalid recipient",
                        "No email should be sent"));

        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void headerInjectionInSubjectIsRejectedBeforeSmtp() {
        assertThrows(
                IllegalArgumentException.class,
                () -> mailer.sendPlain(
                        ALICE,
                        "Subject\r\nBcc: wrong@sample.test",
                        "No message"));

        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void summaryIsDeliveredToToCcAndBccMailboxes()
            throws Exception {

        byte[] content =
                "Nội dung tệp".getBytes(StandardCharsets.UTF_8);

        mailer.sendSummary(
                ALICE, MANAGER, AUDIT,
                "Báo cáo tháng 11",
                "Bản thuần văn bản",
                "<html><body><strong>Báo cáo</strong></body></html>",
                content);

        assertEquals(1L, countMail(ALICE));
        assertEquals(1L, countMail(MANAGER));
        assertEquals(1L, countMail(AUDIT));
        assertEquals(0L, countMail("stranger@sample.test"));

        MimeMessage toCopy = singleMail(ALICE);
        assertEquals(
                List.of(ALICE),
                mailboxes(toCopy.getRecipients(
                        Message.RecipientType.TO)));
        assertEquals(
                List.of(MANAGER),
                mailboxes(toCopy.getRecipients(
                        Message.RecipientType.CC)));

        // Verify Bcc by DELIVERY to the mailbox,
        // DO NOT assert that a Bcc header must appear on the To copy.
        assertEquals(
                "Báo cáo tháng 11", toCopy.getSubject());
    }

    @Test
    void summaryHasUtf8PlainAndHtmlAlternatives()
            throws Exception {

        mailer.sendSummary(
                ALICE, MANAGER, AUDIT,
                "Thông tin tháng 11",
                "Xin chào, nội dung tiếng Việt.",
                "<html><body><b>Xin chào, báo cáo!</b></body></html>",
                "Tệp mẫu".getBytes(StandardCharsets.UTF_8));

        MimeMessage received = singleMail(ALICE);

        String plain = findTextPart(received, "text/plain");
        String html = findTextPart(received, "text/html");

        assertNotNull(plain);
        assertNotNull(html);
        assertEquals(
                "Xin chào, nội dung tiếng Việt.",
                plain.strip());
        assertTrue(html.contains("Xin chào, báo cáo!"));
        assertTrue(received.isMimeType("multipart/*"));
    }

    @Test
    void summaryAttachmentHasNameAndIdenticalBytes()
            throws Exception {

        byte[] expected =
                "Báo cáo số 42\nHợp lệ."
                        .getBytes(StandardCharsets.UTF_8);

        mailer.sendSummary(
                ALICE, null, null,
                "Tệp báo cáo",
                "Có file đính kèm.",
                "<p>Có file đính kèm.</p>",
                expected);

        Part attachment = findAttachment(
                singleMail(ALICE), "summary.txt");

        assertNotNull(attachment);
        assertEquals("summary.txt", attachment.getFileName());
        assertArrayEquals(
                expected,
                attachment.getInputStream().readAllBytes());
    }

    @Test
    void omittedCcAndBccProduceOnlyOneMailbox()
            throws Exception {

        mailer.sendSummary(
                ALICE, null, null,
                "Chỉ To",
                "Nội dung thuần",
                "<p>Nội dung HTML</p>",
                "File".getBytes(StandardCharsets.UTF_8));

        MimeMessage received = singleMail(ALICE);

        assertEquals(
                List.of(ALICE),
                mailboxes(received.getRecipients(
                        Message.RecipientType.TO)));
        assertEquals(
                List.of(),
                mailboxes(received.getRecipients(
                        Message.RecipientType.CC)));
        assertEquals(0L, countMail(MANAGER));
        assertEquals(0L, countMail(AUDIT));
    }

    @Test
    void invalidCcIsRejectedBeforeAnyDelivery() {
        assertThrows(
                IllegalArgumentException.class,
                () -> mailer.sendSummary(
                        ALICE,
                        "invalid-cc",
                        AUDIT,
                        "Bad Cc",
                        "Plain",
                        "<p>HTML</p>",
                        "File".getBytes(StandardCharsets.UTF_8)));

        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void senderUsesDynamicLoopbackSmtpPort() {
        assertTrue(GREEN_MAIL.isRunning());

        JavaMailSenderImpl impl =
                assertInstanceOf(JavaMailSenderImpl.class, sender);

        assertEquals("127.0.0.1", impl.getHost());
        assertEquals(GREEN_MAIL.getSmtp().getPort(),
                impl.getPort());
        assertTrue(impl.getPort() > 0);
        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void emptySubjectIsRejectedWithoutSending() {
        assertThrows(
                IllegalArgumentException.class,
                () -> mailer.sendPlain(
                        ALICE,
                        "   ",
                        "No message"));

        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }

    @Test
    void nullAttachmentIsRejectedWithoutSending() {
        assertThrows(
                NullPointerException.class,
                () -> mailer.sendSummary(
                        ALICE, MANAGER, AUDIT,
                        "Missing attachment",
                        "Plain",
                        "<p>HTML</p>",
                        null));

        assertEquals(0, GREEN_MAIL.getReceivedMessages().length);
    }
}
~~~

**Exact count: 15 `@Test` methods** in one class. `@BeforeEach`, `@AfterAll`, `@DynamicPropertySource`, and helper methods do **not** count toward JUnit test totals. The test class uses `@SpringBootTest` so Boot wires a real `JavaMailSender` and `GreenMail` acts as the mock SMTP server; all traffic goes over the **loopback socket**, never to the Internet.

**Important testing detail:** `GreenMail.findReceivedMessages(...)` filters by `GreenMailUser.getEmail()` (the server-stored mailbox). `getReceivedMessages()` can contain one MIME copy per **recipient mailbox**; checking how many messages landed in a specific mailbox requires `countMail(mailbox)` rather than inferring from total MIME copies. That is why the To/Cc/Bcc tests do not rely solely on `MimeMessage.getAllRecipients()` or an aggregate count.

### 7.1. Helper walkthrough

**`clearMailboxes()`**: calls `purgeEmailFromAllMailboxes()` before each test so old messages never bleed over. Even if a test sends two messages, the next test starts with empty mailboxes. The class runs sequentially under JUnit defaults; if a build enables global JUnit parallelism, isolate GreenMail instances/contexts per test class or annotate with `@Execution(SAME_THREAD)` so concurrent tests cannot purge each other's mail.

**`singleMail(address)`**: enforces **exactly one message** in the target mailbox, checking both delivery count and recipient identity together. If the email goes to the wrong recipient, the helper fails to find it and the test fails.

**`mailboxes(Address[])`**: converts Jakarta Mail `InternetAddress` entries to string addresses to inspect `To`/`Cc`/`From` headers. `getRecipients(...)` returns `null` when a header is absent; the helper normalizes that to `List.of()` for assertions.

**`findTextPart(...)`**: recursively traverses nested `Multipart` structures while skipping parts with `attachment` disposition so a `.txt` attachment is never mistaken for the plain-text body. `MimeMessageHelper.setText(plain, html)` produces an alternative part holding plain and HTML; `helper.addAttachment` adds another MIME part. Because the MIME tree can be `mixed → alternative → text`, directly casting `received.getContent()` to `String` fails.

**`findAttachment(...)`**: locates the part with `Content-Disposition: attachment` and the expected filename; tests read **raw bytes** via `getInputStream()` (Jakarta Mail decodes transfer encodings automatically). Compare bytes directly—never call `.toString()` on a Java `byte[]`.

**Do not assert raw RFC bytes directly** here: JavaMail encodes subjects and bodies automatically, and the application contract covers decoded contents. For S/MIME signing or DKIM systems, add separate tests at the raw-byte canonicalization/signature layer.

### 7.2. Plain-text and negative test cases

| Test | What it checks |
|---|---|
| `plainMailHasToFromSubjectAndUtf8Body` | `To`, `From`, accented `Subject`, UTF-8 plain body |
| `twoDifferentRecipientsDoNotLeakIntoOtherMailbox` | Both intended recipients get mail; unrelated users get none |
| `twoSendsToSameRecipientCreateTwoMessages` | Same recipient receives two copies without accidental deduplication |
| `disabledNotificationDoesNotSendAnyMail` | Feature disabled → **0** messages |
| `enabledNotificationSendsExactlyOneMail` | Feature enabled → exactly 1 message |
| `invalidToIsRejectedBeforeSmtp` | Invalid email syntax → exception + **0** messages |
| `headerInjectionInSubjectIsRejectedBeforeSmtp` | Subject with CR/LF → exception + 0 messages |
| `emptySubjectIsRejectedWithoutSending` | Blank subject → exception + 0 messages |

Negative cases verify **zero SMTP side effects** after validation fails. Asserting only the exception would let an implementation that sends the email first and throws afterward pass falsely.

**Never claim `InternetAddress` syntax validation proves the domain has an MX record.** GreenMail stores mailboxes locally without querying DNS/MX. Production needs dedicated bounce handling and sending policies.

### 7.3. MIME and recipient test cases

| Test | What it checks |
|---|---|
| `summaryIsDeliveredToToCcAndBccMailboxes` | Each To/Cc/Bcc mailbox receives 1 copy; To/Cc headers match |
| `summaryHasUtf8PlainAndHtmlAlternatives` | Both `text/plain` and `text/html` parts contain Unicode text |
| `summaryAttachmentHasNameAndIdenticalBytes` | `summary.txt` attachment carries identical bytes |
| `omittedCcAndBccProduceOnlyOneMailbox` | Optional Cc/Bcc omitted; no stray deliveries |
| `invalidCcIsRejectedBeforeAnyDelivery` | Invalid Cc → 0 messages |

**Bcc tests must verify actual delivery in the Bcc mailbox.** A Bcc header may be stripped from copies sent to other recipients per privacy semantics. Checking only `getRecipients(BCC)` can fail when sending succeeded, or pass when Bcc failed envelope routing. Querying the mailbox directly tests the real requirement.

**Multipart emails** can use varying MIME boundaries and transfer encodings. Traverse `getContent()` and body parts rather than comparing raw SMTP transcripts across runs, because `Message-ID`, `Date`, and boundaries vary.

### 7.4. Configuration test case

`senderUsesDynamicLoopbackSmtpPort` verifies Boot actually wired **`JavaMailSenderImpl`**, `host` is `127.0.0.1`, and `port` matches the running GreenMail server. If a profile or environment accidentally sets `spring.mail.host=smtp.prod.example.com`, this test fails before attempting live sends—a valuable guardrail.

**Why not assert `port != 3025`?** A random port can occasionally land on any specific number. What matters is that the **actual port chosen by GreenMail** matches **`JavaMailSender`'s port**, not avoiding an arbitrary constant.

## 8. Running Gradle, expected results, and evidence

**Prerequisites:** Java 17, compatible Gradle, and initial repository access to download Maven dependencies if uncached. No Docker, PostgreSQL, Mailpit, Gmail/Outlook credentials, or public SMTP network access is required. If a local firewall blocks TCP loopback, connection errors surface right away without opening public SMTP.

If the project has a Gradle Wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you only copied the source files and `build.gradle` **without Gradle Wrapper scripts/JAR**, `./gradlew` will not exist yet. Use an installed Gradle to generate the wrapper or run:

~~~bash
gradle test
~~~

Run this class alone:

~~~bash
./gradlew test --tests demo.mail.NotificationMailerSmtpTest
~~~

Standard Gradle report location:

~~~text
build/reports/tests/test/index.html
~~~

**Expected design outcome:** **15 JUnit Jupiter tests** are discovered and designed to PASS when Gradle, Java, and loopback sockets work properly. There are no `@Disabled` annotations or "always succeeds" mocks. This states **expected behavior derived from source and APIs**, not a claim that Gradle was executed in the reader's environment.

**Observable checks:**
- Plain mail: Alice's mailbox has one message; From/To/Subject/Body decode Unicode accurately.
- Two recipients: Alice and Manager each have one message; Audit and stranger have none.
- Disabled: zero messages across all mailboxes.
- Summary: To/Cc/Bcc each receive one copy; To/Cc headers match; UTF-8 subject preserved.
- HTML: MIME alternatives hold both `text/plain` and `text/html`.
- Attachment: filename `summary.txt`, identical bytes.
- Invalid inputs: exception thrown **before** `sender.send`; GreenMail receives zero emails.
- Dynamic SMTP: `JavaMailSenderImpl.getPort()` matches GreenMail's live SMTP port.

**Timing note:** `JavaMailSender.send` is synchronous here, so by the time it returns normally, the SMTP sandbox has accepted and stored the message. For an `@Async` mail service, wait on a `CompletableFuture`/event or GreenMail's `waitForIncomingEmail(...)` with a timeout rather than asserting immediately after submission.

## 9. Notes on UTF-8, HTML, and attachments

### 9.1. MIME encoded-word subjects

When a subject contains non-ASCII characters, Jakarta Mail serializes the header using RFC 2047 encoded-word format, e.g. raw header strings starting with `=?UTF-8?...?=`. That is **standard wire encoding**; tests should call `MimeMessage.getSubject()` and assert the **decoded value**, not raw encoded Subject bytes.

For email bodies, `MimeMessage.getContent()` returns either `String` or `Multipart` depending on `Content-Type`. Plain emails typically return `String`, while mixed/alternative MIME emails require traversing `Multipart`. The same logical string may travel as quoted-printable or base64; the MIME parser decodes it before tests compare values.

### 9.2. HTML escaping is a separate contract

Code snippet:

~~~java
String html = "<p>Xin chào, <strong>Lan</strong>!</p>";
mailer.sendSummary(
        "alice@sample.test",
        null,
        null,
        "Thông báo HTML",
        "Xin chào, Lan!",
        html,
        "tệp".getBytes(StandardCharsets.UTF_8));
~~~

This is an **auxiliary snippet** calling the demo service. When HTML is rendered from Thymeleaf/Freemarker templates or interpolates user input, ensure **proper HTML escaping** so users cannot inject malicious scripts or links. Email clients also filter HTML, restrict CSS, and block external images; GreenMail tests verify only what the application sends, **never how Gmail or Outlook renders the UI**.

For verification/password-reset links, check:
- HTTPS scheme, host allowlist, exact path, and that tokens are not logged.
- Expiration and single-use semantics belong to authentication logic and need separate tests.
- Never place real tokens or sensitive data in fixtures.
- Include a plain-text alternative when required by contract or accessibility.
- Verify template locale (e.g., `vi-VN`), placeholder substitution, and subjects.

### 9.3. File attachments and `Content-Disposition`

MIME attachments specify filename, media type, transfer encoding, and body bytes. For large files, avoid loading entire payloads into `byte[]` under production memory constraints; use `InputStreamSource`/`FileSystemResource`, and test streaming and size caps. In the demo project, `ByteArrayResource` carries a few bytes for deterministic, path-free tests.

**Never snapshot MIME from a real email containing PII.** Use synthetic data like `"Báo cáo số 42"` and the `.test` domain. When attachments are PDFs or CSVs carrying business data, validate the parsed file contents or compare exact bytes against a known fixture. Never claim a file is valid just because its `.pdf` filename matches—the bytes must also be valid.

### 9.4. Bcc privacy

Bcc recipients must not be exposed in the `To`/`Cc` headers seen by other recipients. Exact Bcc header handling depends on the mail library and RFC-compliant transport: an app may emit separate MIME variants per recipient group or strip the header during transmission. Therefore test:
1. **The Bcc mailbox received the mail** (envelope delivery).
2. **`To`/`Cc` headers contain only the intended addresses**.
3. Bcc addresses are not accidentally printed in the **body/template** or other public headers (inspect raw headers or text content when policy requires).
4. Never require `getRecipients(BCC)` to be populated on the copy delivered to `To`.

In enterprise apps, multi-recipient external emails also require safeguards against misdelivery (DLP, approved domain lists, audit trails). GreenMail tests form one layer of protection, not a complete data-protection policy.

## 10. Preventing accidental real sends in tests

### 10.1. Isolated host and port configuration

In this lesson, `spring.mail.host=127.0.0.1` and `spring.mail.port` come from GreenMail, never reading production `SMTP_HOST`/`SMTP_PASSWORD`. Every address ends with `.test`. A guard test asserts that host and port match GreenMail—concrete evidence of real sandbox wiring.

For stronger CI safety:
- Configure test profiles or validation beans enforcing a local SMTP host.
- Block outbound network egress from test runners/containers except loopback.
- Use fake credentials (or no auth) exclusive to the sandbox.
- Never mount production secrets into test environments.
- Never use real customer emails as test recipients.
- Keep smoke tests against real providers in an isolated, allowlisted, approved pipeline.

**Do not bind GreenMail to `0.0.0.0` unnecessarily.** Bind loopback so the mock server serves only local test processes. Dynamic ports avoid collisions; never hardcode ports 25, 465, or 587 in developer environments.

### 10.2. Testing rejected mail or SMTP errors

The runnable suite focuses on **pre-SMTP validation failures**. To test transport errors:
- Point `JavaMailSenderImpl` at a mock SMTP server **explicitly configured to return error codes** such as 421, 450, or 550 or reject a recipient.
- Assert Spring's `MailException` hierarchy appropriately, **not just error logs**.
- Test retry classifiers: transient 4xx errors may retry per policy, while permanent 5xx errors must not retry endlessly.
- Verify no message lands in the mailbox when SMTP rejects before `DATA`.
- Ensure the mock server starts and stops within the test scope without poisoning the Spring context cache.

**Never suggest testing errors by pointing at production SMTP with a wrong password**: that remains a dangerous external dependency and causes CI flakiness.

### 10.3. Retries and idempotency in email sending

An SMTP server can **accept `DATA`** right before the network drops before the application receives the response. Retrying immediately sends **duplicate emails**. Therefore:
- Never assume an exception from `JavaMailSender.send()` guarantees "the email was definitely not accepted."
- Attach a business notification ID / idempotency key in an outbox/DB when delivery must be tracked.
- Use a durable outbox worker to handle cases where the business transaction commits before sending succeeds.
- Track states (`pending → sending → accepted/failed`), retry budgets, backoff, and correlation logging.
- Avoid generating new verification/reset tokens arbitrarily across retries.
- `Message-ID` helps tracing, yet not all SMTP servers or providers deduplicate by it.
- A GreenMail test can confirm **two sends create two messages**, like `twoSendsToSameRecipientCreateTwoMessages`, guiding where business deduplication belongs.

**Key limitation of "exactly-once email":** there is no default distributed transaction spanning the application database and an external SMTP provider. Real systems aim for **at-least-once attempts + business-level deduplication** or reconciliation via provider APIs within external limits.

## 11. Asynchronous email and test timing

If production sends email via `@Async`:

~~~java
@Async
public CompletableFuture<Void> sendLater(
        String recipient, String subject, String body) {

    mailer.sendPlain(recipient, subject, body);
    return CompletableFuture.completedFuture(null);
}
~~~

This is a **snippet** requiring `@EnableAsync` and invocation via a Spring proxy; it is not part of the runnable project above. In async tests, never call `mailer.sendLater(...)` and assert mailbox counts immediately, as the worker thread may not have finished yet.

Two valid strategies:

1. Use **`CompletableFuture.get(timeout)`** to wait for completion and surface exceptions, then inspect GreenMail mailboxes.
2. When no `Future` is returned (e.g., background worker), use **`greenMail.waitForIncomingEmail(timeoutMillis, expectedCount)`** or Awaitility with a bounded deadline.

~~~java
CompletableFuture<Void> sent = asyncMailer.sendLater(
        "alice@sample.test", "Đã xử lý", "Xin chào");

sent.get(5, TimeUnit.SECONDS);

assertEquals(1L, countMail("alice@sample.test"));
~~~

This is an illustrative snippet assuming `asyncMailer`/`countMail` and full imports in a suitable test class. `Future.get` surfaces worker exceptions directly; with `@Async void` without a `Future`, errors may go only to `AsyncUncaughtExceptionHandler` or logs, making them harder to assert.

**Transaction note:** if a `@Transactional` test swaps the async executor for `SyncTaskExecutor`, emails can be sent inside an open test transaction on the test thread; with a real async worker on another thread, context and transactions do not propagate automatically. An accepted SMTP message **cannot be rolled back by a JDBC transaction**. Avoid sending emails before business transactions commit; use a transactional outbox or after-commit events with failure recovery.

## 12. Verifying templates, locales, and links in emails

An SMTP sandbox verifies final bytes and headers, while production apps also verify business templates:

| Property | Recommended assertion | Risk |
|---|---|---|
| `To` address | Matches normalized authorized account contact/email | Sending to wrong person |
| `Cc`/`Bcc` | Matches roles/opt-in without leakage | Exposing recipient lists |
| `Subject` | Locale, variables, no CRLF injection | Confusing mail or header injection |
| Plain text | Required text present, placeholders substituted | Accessibility / HTML-blocked clients |
| HTML | Content, escaping, link schemes/domains | Injection / phishing |
| Attachment | Filename, MIME type, bytes, size cap | Wrong data or sensitive leaks |
| Send count | 0/1/N per event | Spam, duplicates |
| `From`/`Reply-To` | Authorized sender, valid reply routing | Impersonation / lost replies |
| Unsubscribe/consent | Honors policy per email category | Opt-out / privacy violations |
| Trace/correlation | Message/event ID present, logs redact tokens | Inability to investigate failures |

If an order confirmation formats a currency amount, verify locale/currency formatting on the **rendered text** rather than merely asserting `templateEngine.process(...)` was called. For links containing one-time tokens, test with synthetic tokens and verify URL encoding; never commit snapshots of real tokens.

**Template unit tests and SMTP integration tests complement each other:** template unit tests verify escaping and layout quickly, while GreenMail tests prove `JavaMailSender` ultimately transmits the right headers, body, and attachments to recipients. When an email has a rule like "send only after payment succeeds," test the negative case confirming zero emails on payment failure.

## 13. Common pitfalls and diagnostics

| Symptom | Possible cause | Fix / test |
|---|---|---|
| `NoSuchBeanDefinitionException: JavaMailSender` | Missing `starter-mail` or `spring.mail.host` | Add dependency, set host in test |
| `Connection refused: localhost:3025` | GreenMail not started or wrong hardcoded port | Dynamic port from GreenMail + `@DynamicPropertySource` |
| Tests try reaching corporate SMTP | `spring.mail.host` overridden by profile/env | Guard host/port, enforce network egress rules |
| `javax.mail` fails to compile on Boot 3.3 | Using GreenMail 1.6 or legacy imports | Use Jakarta Mail + GreenMail 2.1.x |
| Subject matches, wrong `To` | Asserted subject without checking mailbox | Verify mailbox per recipient |
| Bcc missing from MIME headers | SMTP transport strips Bcc headers | Assert delivery in Bcc mailbox |
| Total messages = 3, yet wrong recipient | Aggregate count ignores identity | Use `countMail(mailbox)` and negative mailbox checks |
| Casting `getContent()` to `String` fails | Multipart HTML/attachment, not plain text | Traverse nested `Multipart` |
| HTML present, plain text missing | Called `helper.setText(html, true)` only | Call `helper.setText(plain, html)` |
| Garbled Unicode | Wrong MIME charset/encoding or raw-byte check | Configure UTF-8, inspect decoded `getSubject`/`getContent` |
| Attachment exists with wrong bytes | Checked filename only | `getInputStream().readAllBytes()` + `assertArrayEquals` |
| Test polluted by earlier test's mail | Forgot to purge mailboxes | Purge in `@BeforeEach`, isolate tests |
| `@DynamicPropertySource` sees wrong port | Server started after Spring context | Start GreenMail before dynamic supplier runs |
| `@Async` test occasionally finds empty mailbox | Asserted before worker finished | `Future.get` or GreenMail wait with timeout |
| SMTP timeout hangs CI | Infinite JavaMail timeouts | Configure connect/read/write timeouts |
| Mail send exception swallowed | `catch MailException` logs and returns | Explicit retry/failure policy; tests assert errors |
| 550 retried endlessly | Permanent errors not classified | Bounded retries, DLQ/failed notification record |
| Duplicate mail sent on retry | Provider accepted `DATA` before connection drop | Idempotency/outbox/reconciliation |
| Test passes yet Gmail rejects | GreenMail does not verify external deliverability | Dedicated provider sandbox/webhook/smoke tests |
| Logs expose PII | Logged full `MimeMessage` or tokens | Redact logs; use dummy recipients/data |
| Test binds SMTP on `0.0.0.0` | Exposed on public interfaces | Bind `127.0.0.1` in tests |
| Cc/Bcc receive wrong HTML content | Shared template/personalization bug | Assert body per mailbox per policy |
| Spring context cache points to stopped port | Class-scoped GreenMail stopped while context cached | Align scopes or isolate contexts |
| Production STARTTLS fails while GreenMail passes | Sandbox disabled TLS/auth | Dedicated TLS/auth/cert tests |
| Mailpit container needs Docker missing in CI | External mock server dependency | Use embedded GreenMail where appropriate |

### 13.1. Step-by-step debugging workflow

1. Confirm tests actually include `spring-boot-starter-mail` and a `JavaMailSender` bean.
2. Verify `spring.mail.host` is loopback and `spring.mail.port` equals `GREEN_MAIL.getSmtp().getPort()`.
3. Confirm `GREEN_MAIL.isRunning()` is true before sending.
4. Confirm sender SMTP auth/TLS settings match the sandbox configuration.
5. If `JavaMailSender.send` fails, inspect the exception chain and SMTP status code instead of deleting assertions to turn tests green.
6. If sending succeeds but mail is missing, inspect the exact user mailbox rather than aggregate counts.
7. If plain/HTML body assertions fail, walk the MIME multipart tree instead of casting `getContent()` to `String`.
8. If Bcc has no header, check delivery directly in the Bcc mailbox.
9. If Unicode text looks garbled, check the Jakarta Mail version and MIME charset.
10. If tests fail in suite runs, verify pre-method mailbox purging, JUnit parallelism, and Spring context caching.
11. For async sending, await `Future` or GreenMail wait instead of fixed `Thread.sleep(1000)`.
12. For conditional business sends, assert **0 emails** on non-sending branches.
13. Confirm no real recipients/domains or production secrets appear in configs.
14. For production providers, add separate integration tests covering auth, TLS, bounces, and provider APIs.
15. Report results accurately as **SMTP sandbox accepted**, never as "delivered to real inbox."

## 14. Pre-merge review checklist for email code

1. **Recipient correctness:** `To` matches identity, `Cc`/`Bcc` match scope; cover 0, 1, and multiple recipients.
2. **Privacy:** never leak Bcc or PII in public headers, bodies, or logs.
3. **Content:** subject, plain text, HTML, locale, and placeholders verified after rendering.
4. **Attachment:** filename, media type, bytes, size limits, and retention validated.
5. **Transport:** host, port, and test mode genuinely target the sandbox, never live SMTP.
6. **Spring bean:** auto-configured or custom `JavaMailSender` wiring verified.
7. **Timeouts:** finite SMTP connect/read/write timeouts configured.
8. **Negative paths:** disabled features and validation failures send zero emails.
9. **Count:** assert exact 0/1/N messages and verify unrelated mailboxes remain empty.
10. **Async:** wait on completion and observe exceptions; never use sleeps as signals.
11. **Retries:** retry budgets, backoff, idempotency, outbox, and accepted/failed states are clear.
12. **Failure injection:** SMTP 4xx/5xx, connection resets, and provider outages tested at the right layer.
13. **Security:** no real tokens, PII, or SMTP passwords in test fixtures or logs.
14. **Lifecycle:** start server before Spring context, purge between tests, stop after class.
15. **Compatibility:** Java 17, Spring Boot 3.3.5, Jakarta Mail, and GreenMail 2.1.x APIs align.
16. **Claims:** never confuse sandbox acceptance with external inbox delivery.

## 15. Extension exercises

**Exercise 1 — Wrong `To` detection:** Change `sendPlain(ALICE,...)` to `sendPlain(MANAGER,...)`. Which test catches it? If you only checked `getReceivedMessages()[0].getSubject()`, why would it slip through?

**Exercise 2 — Two recipients:** Send two emails to Alice and Manager; assert each mailbox holds 1 message and Audit holds 0. If both went to Alice, which test catches it?

**Exercise 3 — Cc/Bcc:** Remove `helper.setBcc(bcc)` in the service. Why must tests inspect the Bcc mailbox rather than looking for a Bcc header?

**Exercise 4 — Unicode:** Change the subject to `"Thông báo: Đã thanh toán – tháng 11"` with accented body text. Verify decoded subject/body rather than comparing raw RFC 2047 encoded headers.

**Exercise 5 — Multipart:** Drop `.setText(plain, html)` and send HTML only. When the MIME parser searches for `text/plain`, what does it find and which test fails?

**Exercise 6 — Attachments:** Alter the attachment bytes while keeping filename `summary.txt`. Why would a test checking only the filename pass falsely?

**Exercise 7 — Validation:** Send a subject containing CRLF or an invalid address. Assert **both the exception and 0 sent emails**, not just the exception.

**Exercise 8 — Unsubscribe:** Simulate an opted-out marketing email. Ensure `sendIfEnabled(false)` has zero SMTP side effects and record an audit reason for skipping.

**Exercise 9 — Dynamic port:** Run two test suites concurrently on CI. Explain why a random port is safer than 3025, yet `ApplicationContext` caching and cleanup isolation are still required.

**Exercise 10 — SMTP auth:** Configure GreenMail with a username/password and enable AUTH. Test success with dummy credentials and failure with a wrong password—never against real SMTP.

**Exercise 11 — TLS:** Set up an SMTPS/STARTTLS sandbox and test TLS handshakes and certificate policies. Why can't a TLS-disabled test prove production transport security?

**Exercise 12 — Async:** Wrap `sendPlain` in `@Async` returning `CompletableFuture`. Wait for completion, assert exactly 1 email, and add a worker-exception test.

**Exercise 13 — Retries:** Simulate a temporary SMTP 451 failure followed by 250. Verify retry logic avoids sending duplicates when the server accepted `DATA` before a connection reset.

**Exercise 14 — Outbox:** Persist a notification event in the database inside the business transaction and relay the email after commit; simulate crashes before and mid-send to test idempotency.

**Exercise 15 — Template engine:** Render a localized notification via Thymeleaf/Freemarker with a dummy URL/token; verify HTML escaping and link host allowlists on the message received by GreenMail.

**Exercise 16 — Attachment types:** Swap `.txt` for PDF/CSV; check content-type, filename, bytes, and verify no other user's document leaks.

**Exercise 17 — Provider callbacks:** When a provider emits delivered/bounced/complained webhooks, test webhook signature verification, idempotency, and state transitions separately. Embedded GreenMail does not simulate inbox or complaint lifecycles.

**Exercise 18 — QA checklist:** Build a requirements matrix covering To/Cc/Bcc, subject, locale, template body, attachment, no-send branches, SMTP errors, and retries, mapping each requirement to a concrete test name.

## 16. Official references

- [Spring Boot 3.3 — Sending Email](https://docs.spring.io/spring-boot/3.3/reference/io/email.html): `JavaMailSender`, `spring.mail.*`, timeouts, and auto-configuration.
- [Spring Framework 6.1 — Email](https://docs.spring.io/spring-framework/reference/integration/email.html): `MailSender`, `JavaMailSender`, `SimpleMailMessage`, `MimeMessageHelper`.
- [Spring Framework — `MimeMessageHelper` API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/mail/javamail/MimeMessageHelper.html): To/Cc/Bcc, multipart, `text/plain`/`text/html`, attachments, encoding.
- [Spring Framework — `JavaMailSenderImpl` API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/mail/javamail/JavaMailSenderImpl.html): host, port, protocol, send.
- [Spring Test — `@DynamicPropertySource`](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): dynamic properties before `ApplicationContext` creation.
- [GreenMail Official Documentation](https://greenmail-mail-test.github.io/greenmail/): embedded SMTP, Jakarta Mail compatibility, dynamic ports, JUnit test examples.
- [GreenMail 2.1 — `GreenMail` API](https://javadoc.io/static/com.icegreen/greenmail/2.1.0/com/icegreen/greenmail/util/GreenMail.html): received messages, `findReceivedMessages`, purge, start/stop.
- [GreenMail 2.1 — `ServerSetup` API](https://javadoc.io/static/com.icegreen/greenmail/2.1.0/com/icegreen/greenmail/util/ServerSetup.html): `dynamicPort`, `getPort`, binding.
- [Jakarta Mail — `Message` API](https://jakarta.ee/specifications/mail/2.1/apidocs/jakarta.mail/jakarta/mail/message): `RecipientType`, `getRecipients`, `getFrom`, MIME.
- [Jakarta Mail — `Part` API](https://jakarta.ee/specifications/mail/2.1/apidocs/jakarta.mail/jakarta/mail/part): multipart/body parts, attachments, content.
- [JUnit Jupiter User Guide](https://docs.junit.org/5.11.4/user-guide/): lifecycle annotations, assertions, Gradle/JUnit Platform.
- [IETF RFC 5321 — SMTP](https://www.rfc-editor.org/rfc/rfc5321): SMTP envelope and delivery.
- [IETF RFC 5322 — Internet Message Format](https://www.rfc-editor.org/rfc/rfc5322): `To`/`Cc`/`Bcc` message headers.
- [IETF RFC 2045/2046 — MIME](https://www.rfc-editor.org/rfc/rfc2045): content types, transfer encodings, multipart semantics.

**Remember:** Good email tests answer **"what was sent, to which mailbox, how many copies, and with what bytes/content?"** `JavaMailSender` + a **GreenMail SMTP sandbox** delivers far stronger evidence than mocking `send`: tests verify **To/Cc/Bcc envelope delivery, Unicode subjects and bodies, multipart HTML/plain parts, attachments, and zero-send paths**. Still, GreenMail verifies delivery only to a **test-only mock SMTP server**, not Gmail/Outlook inboxes. Always bind localhost + dynamic ports, purge mailboxes, configure timeouts, and write separate tests for provider auth/TLS, bounces, and retry/idempotency when reliability is required.