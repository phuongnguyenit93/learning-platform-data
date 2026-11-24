# Building a Plain-Text MailService with SimpleMailMessage

This practice lesson guides you through building a **MailService** in a **Spring Boot** application to send **plain-text** emails using `org.springframework.mail.SimpleMailMessage`. Learners will define a clear service contract, configure `JavaMailSender` via Spring Boot, test sending against a local SMTP sandbox, verify message content with Mockito, and understand the limitations of synchronous sending in real deployments.

Desired outcome:

~~~java
mailService.sendPlainText(
    new PlainTextMailCommand(
        "learner@example.net",
        "Registration confirmation",
        "Hello!\nYour account has been created."));
~~~

The service class converts the command into:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom(fromAddress);
message.setTo(command.to());
message.setSubject(command.subject());
message.setText(command.body());
javaMailSender.send(message);
~~~

The code looks simple, yet a production-usable design must answer: **Where does `From` come from? Who is allowed to call the service? Is the recipient address valid? If sending fails, how does the caller know? Do unit tests send real emails? Does SMTP accepted mean delivered?**

**Lesson scope:** build a service that sends text immediately over SMTP, without implementing HTML/attachments, queues, or a transactional outbox yet. Production extensions are explained separately so practice examples are not mistaken for exactly-once guarantees.

## 1. Business Scenario and Learning Objectives

Suppose a small ordering application needs to send an email when a customer registers:

~~~text
From: no-reply@example.test
To: learner@example.net
Subject: Account confirmation

Hello,

Your account has been created successfully.
Please sign in and start using the service.

Best regards,
Support Team
~~~

Instead of having each `AccountService`, `OrderService`, or `NotificationController` construct emails itself, we create a dedicated mail module:

~~~text
Local test API / Business Service
                 |
                 v
        MailService interface
                 |
                 v
    SmtpPlainTextMailService
                 |
        new SimpleMailMessage
                 |
                 v
          JavaMailSender
                 |
                 v
       SMTP sandbox / provider
~~~

After this lesson, you should be able to:

1. Understand the role of `SimpleMailMessage` and when to switch to `MimeMessageHelper`.
2. Add dependencies and configure sender, host, port, TLS, credentials, and timeouts.
3. Write a reusable, easily mockable `MailService` without hardcoding secrets.
4. Send an email with `From`, `To`, `Subject`, and `Text`.
5. Use a local SMTP server to inspect emails without sending to the Internet.
6. Write unit tests verifying the exact message object.
7. Distinguish submission success from delivery, classify errors, and recognize production security requirements.

## 2. How Does SimpleMailMessage Work?

`SimpleMailMessage` is a Spring Mail class used to represent a simple plain-text email. It holds common fields without requiring the caller to handle MIME multipart directly.

| Method | Purpose | Example |
| --- | --- | --- |
| `setFrom(String)` | Sender address | `no-reply@example.test` |
| `setTo(String...)` | One or more primary recipients | `learner@example.net` |
| `setCc(String...)` | Carbon copy | `manager@example.net` |
| `setBcc(String...)` | Blind carbon copy | `audit@example.net` |
| `setReplyTo(String)` | Reply-to address | `support@example.test` |
| `setSubject(String)` | Subject | `Registration confirmation` |
| `setText(String)` | Plain-text body | `Hello!` |
| `setSentDate(Date)` | Sent date if set explicitly | Usually left for the mail sender |

In this lesson, only `From`, `To`, `Subject`, and `Text` are needed. The other fields are introduced in the extension sections.

### 2.1. SimpleMailMessage vs. MimeMessage

| Capability | SimpleMailMessage | MimeMessage + MimeMessageHelper |
| --- | --- | --- |
| Send plain text | Yes | Yes |
| Send true HTML | No | Yes |
| Attach PDF/images | No | Yes |
| Inline images via Content-ID | No | Yes |
| Control MIME multipart | Not directly | Yes |
| Ease of learning/testing | High | Requires MIME understanding |

Note: 

~~~java
message.setText("<h1>Hello</h1>");
~~~

is still **plain text**; it does not automatically become HTML content. Mail clients may display the literal string `<h1>Hello</h1>`. For HTML, use `MimeMessageHelper.setText(plainText, htmlText)` and an appropriate MIME multipart structure.

### 2.2. MailSender and JavaMailSender

Spring provides `MailSender` for `SimpleMailMessage`. `JavaMailSender` is an extended interface supporting both `SimpleMailMessage` and `jakarta.mail.internet.MimeMessage`.

Spring Boot starter-mail typically auto-configures a suitable `JavaMailSenderImpl` when `spring.mail.host` is supplied, which the service then injects via its constructor:

~~~java
private final JavaMailSender javaMailSender;
~~~

You do not need to create an SMTP connection or a Jakarta Mail `Session` directly inside each business method.

### 2.3. Never Share SimpleMailMessage Across Threads

`SimpleMailMessage` is a **mutable** object. Never declare:

~~~java
@Service
public class BadMailService {
    private final SimpleMailMessage shared =
            new SimpleMailMessage();
}
~~~

and mutate `To`, `Subject`, and `Text` on the same object across multiple requests. Two threads can corrupt each other's recipient/body data.

**Correct:** create `new SimpleMailMessage()` for each send. A singleton Spring service remains safe when it holds only immutable sender/config state.

## 3. Sample Project Structure

The example uses Java 17+, Spring Boot 3.x, Spring Framework 6.x, and the `jakarta.*` namespace for Jakarta Validation.

~~~text
mail-demo/
  build.gradle
  src/
    main/
      java/com/example/maildemo/
        MailDemoApplication.java
        mail/
          MailService.java
          PlainTextMailCommand.java
          SmtpPlainTextMailService.java
        web/
          SendPlainTextMailRequest.java
          SendPlainTextMailResponse.java
          LocalMailController.java
      resources/
        application.yml
        application-local.yml
        application-prod.yml
    test/
      java/com/example/maildemo/mail/
        SmtpPlainTextMailServiceTest.java
~~~

### 3.1. Gradle Dependencies

In `build.gradle` of a Spring Boot project with appropriate dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the `dependencies` block, not the entire `build.gradle`. Configure the Spring Boot plugin and Java toolchain per your project version. If `MailService` is called only from business services without REST, `spring-boot-starter-web` can be omitted.

### 3.2. Maven Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Use the matching Spring Boot parent/BOM version to manage Spring Mail, Jakarta Mail, and testing libraries. Do not mix legacy `javax.mail` from older projects with `jakarta.mail` from Spring Boot 3.

### 3.3. Main Class

`MailDemoApplication.java`:

~~~java
package com.example.maildemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MailDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MailDemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` scans components in `com.example.maildemo` and its subpackages. Once an SMTP host is configured in a profile, Spring Boot normally auto-configures `JavaMailSender`; you do not instantiate it manually in controllers.

## 4. Separating Local and Production Configuration

In this project, we intentionally leave out any default SMTP account in shared configuration. Run the `local` profile to send to a sandbox, or `prod` when real infrastructure is ready. Never accidentally send production emails while testing.

### 4.1. application.yml

~~~yaml
spring:
  application:
    name: mail-demo

# Run with --spring.profiles.active=local or prod.
~~~

### 4.2. application-local.yml

`src/main/resources/application-local.yml`:

~~~yaml
server:
  address: 127.0.0.1

spring:
  mail:
    host: 127.0.0.1
    port: 1025
    protocol: smtp
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "false"
      "[mail.smtp.starttls.enable]": "false"
      "[mail.smtp.starttls.required]": "false"
      "[mail.smtp.connectiontimeout]": "3000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"

app:
  mail:
    from: no-reply@example.test
~~~

Purpose: connect to a local SMTP server such as Mailpit on port 1025 without credentials and without sending real mail onto the Internet. Plaintext in a local sandbox is an option **strictly for an isolated test environment**, not a template for production.

`server.address=127.0.0.1` binds the demo web endpoint to the host's loopback interface. When running in Docker or remote development, inspect network mappings carefully so you do not inadvertently expose the endpoint.

### 4.3. application-prod.yml

`src/main/resources/application-prod.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    protocol: smtp
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"

app:
  mail:
    from: ${MAIL_FROM}
~~~

This is an example for SMTP submission supporting **STARTTLS on port 587**. For SMTP providers using **implicit TLS on port 465**, adjust the mode accordingly (such as `mail.smtp.ssl.enable=true`) and use the port/hostname specified in the provider's documentation.

Notes:

- `SMTP_HOST` must be a valid hostname matching the TLS certificate.
- `SMTP_USERNAME` and `SMTP_PASSWORD` come from secret management/environment variables; never commit them to Git.
- `MAIL_FROM` must be an address the SMTP account is authorized to use.
- `mail.smtp.starttls.required=true` prevents falling back to plaintext if STARTTLS cannot be negotiated per policy.
- `mail.smtp.ssl.checkserveridentity=true` enforces server hostname verification.
- Never add `mail.smtp.ssl.trust=*` or a trust-all manager to bypass certificate errors.
- Timeouts bound network stalls; they do not prove an email was not received by the relay when a timeout occurs at the end of a transaction.

### 4.4. Quick Configuration Reference

| Property | Purpose |
| --- | --- |
| `spring.mail.host` | SMTP relay endpoint |
| `spring.mail.port` | Port matching TLS mode |
| `spring.mail.username/password` | SMTP authentication credentials |
| `spring.mail.default-encoding` | Charset for Unicode handling |
| `mail.smtp.auth` | Require SMTP AUTH |
| `mail.smtp.starttls.enable` | Enable STARTTLS |
| `mail.smtp.starttls.required` | Enforce STARTTLS when configured |
| `mail.smtp.ssl.checkserveridentity` | Verify server hostname |
| `mail.smtp.connectiontimeout` | Connection timeout |
| `mail.smtp.timeout` | Read timeout |
| `mail.smtp.writetimeout` | Write timeout |
| `app.mail.from` | Application-controlled From address |

JavaMail properties use bracket notation in YAML to preserve dots in keys when Spring Boot binds Map properties.

## 5. Designing PlainTextMailCommand

Business services should pass a **clearly defined** request object rather than manipulating mutable message objects directly.

`mail/PlainTextMailCommand.java`:

~~~java
package com.example.maildemo.mail;

import java.util.Objects;

public record PlainTextMailCommand(
        String to,
        String subject,
        String body) {

    public PlainTextMailCommand {
        Objects.requireNonNull(to, "to");
        Objects.requireNonNull(subject, "subject");
        Objects.requireNonNull(body, "body");

        if (to.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient must not be blank");
        }
        if (subject.isBlank() || subject.length() > 200) {
            throw new IllegalArgumentException(
                    "Invalid subject length");
        }
        if (subject.contains("\r") || subject.contains("\n")) {
            throw new IllegalArgumentException(
                    "Subject must not contain newlines");
        }
        if (body.isBlank() || body.length() > 10000) {
            throw new IllegalArgumentException(
                    "Invalid body length");
        }
    }
}
~~~

Significance:

- `record` keeps command data immutable across its String fields.
- `Objects.requireNonNull` catches invalid inputs early.
- Subject forbids CR/LF to prevent injecting arbitrary newlines into headers.
- Body is allowed to contain normal newlines.
- `200` characters for subject and `10000` characters for body are **illustrative application limits**, not universal SMTP limits.

This is not yet complete email address validation. The web layer will use `@Email`, while callers from message consumers or business services must go through equivalent validation and authorization.

## 6. Defining MailService

`mail/MailService.java`:

~~~java
package com.example.maildemo.mail;

public interface MailService {
    void sendPlainText(PlainTextMailCommand command);
}
~~~

Method contract:

- Accepts a valid command from an authorized caller.
- Executes one **send call** over the configured SMTP transport.
- If `JavaMailSender` completes normally, the method returns.
- If a `MailException` or related failure occurs, the caller receives the exception to handle explicitly.

`void` is reasonable at this example level because `JavaMailSender.send(SimpleMailMessage)` returns neither a delivery receipt nor a provider message ID. Do not rename the method to `deliverEmail`, because **SMTP submitted does not mean delivered**.

If you later implement an outbox, a different interface might be:

~~~java
EnqueueResult enqueue(MailCommand command);
~~~

returning a job ID with status `PENDING`. In that model, enqueue success means durably persisting the request, not calling SMTP.

## 7. Implementing SmtpPlainTextMailService

`mail/SmtpPlainTextMailService.java`:

~~~java
package com.example.maildemo.mail;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class SmtpPlainTextMailService implements MailService {

    private final JavaMailSender javaMailSender;
    private final String fromAddress;

    public SmtpPlainTextMailService(
            JavaMailSender javaMailSender,
            @Value("${app.mail.from}") String fromAddress) {

        this.javaMailSender = Objects.requireNonNull(
                javaMailSender, "javaMailSender");

        if (fromAddress == null || fromAddress.isBlank()) {
            throw new IllegalArgumentException(
                    "app.mail.from must be configured");
        }
        this.fromAddress = fromAddress;
    }

    @Override
    public void sendPlainText(PlainTextMailCommand command) {
        Objects.requireNonNull(command, "command");

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setTo(command.to());
        message.setSubject(command.subject());
        message.setText(command.body());

        javaMailSender.send(message);
    }
}
~~~

This is the core of the practice project. We do not manually construct a Jakarta Mail `Session`, embed SMTP credentials in the service, or hold a mutable `SimpleMailMessage` as a singleton field.

### 7.1. Step-by-Step Explanation

1. `@Service` registers the Spring bean.
2. Inject `JavaMailSender` via constructor so it can be replaced with a mock in unit tests.
3. Inject `app.mail.from` from profile-separated configuration.
4. Validate that `From` is non-blank at bean creation time.
5. Create a fresh `SimpleMailMessage` on every call.
6. `setFrom` uses the server-managed sender identity.
7. `setTo` uses the validated command recipient.
8. `setSubject` and `setText` set the subject and plain-text body.
9. `javaMailSender.send(message)` asks the transport to perform SMTP submission.

### 7.2. Why Not Let Callers Choose From?

In a real application, a REST caller must not be able to pass:

~~~json
{
  "from": "ceo@unrelated-domain.example",
  "to": "someone@example.org",
  "subject": "Important",
  "body": "..."
}
~~~

This enables spoofing or causes the SMTP provider to reject the message due to an unverified sender. If the application has multiple valid sender addresses, use an authorized **sender profile** or allowlisted configuration, never trusting arbitrary `From` addresses from the request body.

### 7.3. Why Not Catch and Swallow Exceptions?

An anti-pattern:

~~~java
try {
    javaMailSender.send(message);
} catch (Exception ex) {
    logger.warn("Email failed");
}
// Caller still thinks the operation succeeded.
~~~

When a service swallows exceptions and returns normally, the caller has no idea SMTP submission failed. In this lesson, we let `MailException` propagate. In production, the orchestration layer intentionally handles retries, alerts, and job state.

### 7.4. Never Log the Entire Email

Do not log the full `SimpleMailMessage` object if it contains recipient addresses, OTPs, reset tokens, or invoice data. Prefer minimal metadata such as mail type, sender profile, correlation ID, and error class. Passwords and API tokens must never be logged.

## 8. Adding a Local-Only Practice REST Endpoint

To make testing easy to observe, add a controller **active only when the `local` profile is enabled**. This endpoint is a learning tool, **not a safe public mail API**. An endpoint allowing outsiders to send to arbitrary recipients without authentication and rate limiting can become a spam tool or open relay.

### 8.1. Request DTO

`web/SendPlainTextMailRequest.java`:

~~~java
package com.example.maildemo.web;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SendPlainTextMailRequest(
        @NotBlank @Email
        String to,

        @NotBlank @Size(max = 200)
        String subject,

        @NotBlank @Size(max = 10000)
        String body) {
}
~~~

`@NotBlank` ensures the field has content; `@Email` checks address syntax; `@Size` bounds input length. Validators do not prove a mailbox exists and do not replace authorization or anti-abuse controls.

### 8.2. Response DTO

`web/SendPlainTextMailResponse.java`:

~~~java
package com.example.maildemo.web;

public record SendPlainTextMailResponse(
        String status) {
}
~~~

### 8.3. Controller

`web/LocalMailController.java`:

~~~java
package com.example.maildemo.web;

import com.example.maildemo.mail.MailService;
import com.example.maildemo.mail.PlainTextMailCommand;
import jakarta.validation.Valid;

import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("local")
@RequestMapping("/api/local/mail")
public class LocalMailController {

    private final MailService mailService;

    public LocalMailController(MailService mailService) {
        this.mailService = mailService;
    }

    @PostMapping("/plain")
    public ResponseEntity<SendPlainTextMailResponse> send(
            @Valid @RequestBody SendPlainTextMailRequest request) {

        PlainTextMailCommand command =
                new PlainTextMailCommand(
                        request.to(),
                        request.subject(),
                        request.body());

        mailService.sendPlainText(command);

        return ResponseEntity.ok(
                new SendPlainTextMailResponse(
                        "SUBMITTED_TO_SMTP"));
    }
}
~~~

If `JavaMailSender.send(...)` throws an error, the method does not return a success response. Other HTTP responses must be defined by an exception mapper or server policy.

The demo status `SUBMITTED_TO_SMTP` indicates that the transport call **returned normally**; it does not prove the email was delivered to the Inbox or read. For any production API, clearly define submitted, queued, and delivered states.

### 8.4. Why Enable Only in Local?

`@Profile("local")` prevents the controller from being registered when running only the `prod` profile. In `application-local.yml`, `server.address=127.0.0.1` restricts the listener to the loopback host. However, that is **not** a complete authorization mechanism. Never run `local` and `prod` profiles together and expose the endpoint publicly.

In a larger application, business services can invoke `MailService` directly after authorizing the operation. If a production mail-sending endpoint is required, you must add authentication, authorization, tenant isolation, an allowlist/destination policy, rate limiting, auditing, and idempotency.

## 9. Testing Through Mailpit Locally

To avoid using real email accounts, run an **SMTP sandbox**. Mailpit is a popular choice; for example, it provides an SMTP listener on port 1025 and a web UI on port 8025.

If Docker is installed:

~~~bash
docker run --rm --name mailpit-demo \
  -p 127.0.0.1:1025:1025 \
  -p 127.0.0.1:8025:8025 \
  axllent/mailpit:latest
~~~

This is strictly a **learner reference command**, not a command executed while authoring the lesson. Verify the image and ports against current Mailpit documentation. Ports are bound to loopback to reduce the risk of exposing the SMTP sandbox to an external network.

Sandbox UI (per the example configuration):

~~~text
http://127.0.0.1:8025
~~~

### 9.1. Running the Application with the Local Profile

With Gradle:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=local'
~~~

With Maven:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
~~~

If the app uses the default HTTP port 8080, the endpoint is at `http://127.0.0.1:8080/api/local/mail/plain`.

### 9.2. Sending an HTTP Request

~~~bash
curl -i -X POST http://127.0.0.1:8080/api/local/mail/plain \
  -H "Content-Type: application/json" \
  -d '{
    "to": "learner@example.net",
    "subject": "Thử nghiệm SimpleMailMessage",
    "body": "Xin chào,\nĐây là email plain text từ Spring Boot."
  }'
~~~

If the sandbox accepts the email and the sender encounters no error, the demo response may be:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"SUBMITTED_TO_SMTP"}
~~~

Open `http://127.0.0.1:8025` to inspect the newly arrived email. With Mailpit, the test recipient does not need to exist on the Internet; the sandbox mailbox holds test data solely for inspection.

### 9.3. What to Observe

1. Is `From` exactly `no-reply@example.test`?
2. Is `To` exactly `learner@example.net`?
3. Does the Subject display Vietnamese and diacritics properly?
4. Does the body preserve diacritics and line breaks?
5. Is the email plain text with no HTML part?
6. Did one POST produce exactly one email without unexpected duplicates?

Inspect only in the local sandbox; never send test content to real users' mailboxes without permission.

### 9.4. Running Inside Docker vs. on the Host

If the Spring app also runs inside a container:

~~~text
127.0.0.1 inside Spring container = the Spring container itself
127.0.0.1 on the host             = the host machine
~~~

Therefore, `spring.mail.host=127.0.0.1` inside the Spring container will not point to the Mailpit container. Configure a shared Docker network and the appropriate service hostname, such as `mailpit` in a Compose network (if the service actually has that name). Never expose the SMTP sandbox port to the Internet to work around networking confusion.

### 9.5. Quick Failure Scenario

Stop Mailpit and call the endpoint again. `JavaMailSender.send(...)` will throw a connection error rather than completing. Never "fix" this by catching the exception and still returning `SUBMITTED_TO_SMTP`.

**The following sections cover automated testing, error handling, and production extensions for the service we built.**

## 10. Unit Testing MailService with JUnit and Mockito

Because `SmtpPlainTextMailService` receives `JavaMailSender` via its constructor, the real sender can be swapped for a Mockito mock. This is a key design benefit: **testing email construction logic without network connections or sending real mail**.

`src/test/java/com/example/maildemo/mail/SmtpPlainTextMailServiceTest.java`:

~~~java
package com.example.maildemo.mail;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.MailException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class SmtpPlainTextMailServiceTest {

    @Mock
    private JavaMailSender javaMailSender;

    @Test
    void sendsPlainTextWithExpectedFields() {
        MailService service =
                new SmtpPlainTextMailService(
                        javaMailSender,
                        "no-reply@example.test");

        service.sendPlainText(
                new PlainTextMailCommand(
                        "learner@example.net",
                        "Notification",
                        "Hello!\nThis is plain-text content."));

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(
                        SimpleMailMessage.class);

        verify(javaMailSender).send(captor.capture());

        SimpleMailMessage actual = captor.getValue();

        assertEquals(
                "no-reply@example.test",
                actual.getFrom());
        assertArrayEquals(
                new String[]{"learner@example.net"},
                actual.getTo());
        assertEquals(
                "Notification",
                actual.getSubject());
        assertEquals(
                "Hello!\nThis is plain-text content.",
                actual.getText());
    }

    @Test
    void propagatesMailException() {
        MailService service =
                new SmtpPlainTextMailService(
                        javaMailSender,
                        "no-reply@example.test");

        doThrow(new MailSendException(
                "SMTP sandbox unavailable"))
                .when(javaMailSender)
                .send(any(SimpleMailMessage.class));

        assertThrows(
                MailException.class,
                () -> service.sendPlainText(
                        new PlainTextMailCommand(
                                "learner@example.net",
                                "Error notification",
                                "Test content")));
    }
}
~~~

### 10.1. Why Use ArgumentCaptor?

`verify(javaMailSender).send(captor.capture())` extracts the exact `SimpleMailMessage` instance passed to the mock. The test then verifies:

- `From` matches configuration;
- `To` matches the command;
- `Subject` is accurate;
- `Text` is preserved, including Unicode and line breaks;
- `send(...)` was invoked;
- no real SMTP connection occurred.

This is far more accurate than a test that merely invokes the service and asserts "no exception thrown": a default mock never throws and could hide a wrong recipient bug.

### 10.2. Testing a Subject with Newlines

Add a test for the command:

~~~java
@Test
void rejectsSubjectWithLineBreaks() {
    assertThrows(
            IllegalArgumentException.class,
            () -> new PlainTextMailCommand(
                    "learner@example.net",
                    "Hello\r\nBcc: hidden@example.org",
                    "Content"));
}
~~~

The constructor is expected to reject it before the SMTP sender is ever called. The body is still permitted to contain normal newlines.

### 10.3. Testing Two Independent Sends

For a singleton service, verify that two consecutive commands never mix data:

~~~java
MailService service =
        new SmtpPlainTextMailService(
                javaMailSender, "no-reply@example.test");

service.sendPlainText(
        new PlainTextMailCommand(
                "first@example.net", "First", "Body A"));
service.sendPlainText(
        new PlainTextMailCommand(
                "second@example.net", "Second", "Body B"));
~~~

In the test, capture both invocations and verify each message contains its own data and the two objects are not the same reference. This check effectively catches the shared mutable `SimpleMailMessage` field anti-pattern.

### 10.4. What Unit Tests Do Not Prove

Unit tests do not verify:

- that the SMTP host/port is reachable;
- that STARTTLS, certificate chains, and SMTP AUTH are valid;
- that text is encoded properly on the wire;
- that the provider accepted the email;
- that the message reached the recipient's mailbox.

Integration tests are needed to cover the remaining layers.

## 11. Integration Testing with a Fake SMTP Server

An integration test can run Mailpit, GreenMail, or an SMTP sandbox container inside the test environment. Flow:

~~~text
Start isolated SMTP test server
          |
          v
Configure JavaMailSender host/port
          |
          v
Call MailService.sendPlainText(...)
          |
          v
Test server receives message
          |
          v
Assert From/To/Subject/Text/charset
          |
          v
Cleanup server/mailbox/fixtures
~~~

### 11.1. Key Integration Scenarios

| Scenario | What to Verify |
| --- | --- |
| Simple email | SMTP server receives exactly one message |
| Vietnamese text | Subject/body decode properly as UTF-8 |
| Multi-line body | Newlines are preserved per MIME |
| SMTP server down | Service throws `MailException` or appropriate error |
| Wrong SMTP password | Authentication error is classified |
| Invalid From | Provider rejects per policy, never returns success |
| STARTTLS required but unsupported | No fallback to plaintext |
| Sending multiple messages | No cross-contamination of recipients/bodies |
| Timeout/network reset | Do not assert the email was definitely not received |

### 11.2. Waiting on Conditions

In asynchronous tests, avoid assuming the email arrives immediately after `Thread.sleep(1000)`. Wait with a bounded timeout on an actual condition such as "mailbox contains a message carrying the test correlation ID", using Awaitility or a suitable test polling mechanism.

Even when this lesson sends synchronously, running an SMTP test server in a separate container can introduce slight latency before the mailbox API shows the message; tests should handle that with a finite timeout.

### 11.3. Never Use Real SMTP in CI

CI should never rely on personal accounts or send emails to real users. Use a sandbox with an explicit lifecycle, dedicated fixture recipients, and cleanup. If a real provider E2E test is truly required, use an authorized sandbox/tenant account and isolate it from the unit-test pipeline.

### 11.4. Goals of the Three Test Layers

1. **Unit tests:** mock `JavaMailSender` to verify `SimpleMailMessage` construction.
2. **Integration tests:** fake SMTP server to verify protocol and MIME/encoding.
3. **Provider tests:** verify credentials, TLS, sender permissions, provider policies, and delivery events per provider documentation.

No single test replaces all three layers.

## 12. Spring Mail Exceptions and How to Handle Them

`JavaMailSender.send(...)` can throw subclasses of `org.springframework.mail.MailException`. Underlying causes from Jakarta Mail/SMTP often sit inside nested exceptions.

| Error Type / Symptom | Common Meaning | Handling Suggestion |
| --- | --- | --- |
| `MailAuthenticationException` | SMTP AUTH failed | Credentials/OAuth/account permissions |
| `MailSendException` | Error occurred while sending | Inspect nested cause and per-message failures |
| `MailParseException` | Failed to prepare/parse message | Check recipients, headers, MIME/input |
| `MailPreparationException` | Error during message preparation in related APIs | Fix preparation data/code |
| `ConnectException` | TCP connection refused | Host/port/service not listening |
| `SocketTimeoutException` | Connect/read/write timed out | Network/provider issue; outcome may be uncertain |
| `SSLHandshakeException` | TLS chain/hostname/protocol error | Fix certificate/TLS mode/truststore |
| SMTP `535` | Authentication unsuccessful | SMTP account/OAuth |
| SMTP `550`, `553` | Often policy/recipient/sender rejection | Classify from provider response |

Never use the outer exception class name alone to conclude an email was definitely not sent. For instance, a timeout occurring after the relay receives `DATA` but before the app reads the final response leaves an uncertain state.

### 12.1. A Handler That Must Not Hide Errors

If the web layer needs to standardize error responses:

~~~java
package com.example.maildemo.web;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.mail.MailException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@Profile("local")
@RestControllerAdvice
public class LocalMailErrorHandler {

    @ExceptionHandler(MailException.class)
    public ResponseEntity<String> mailFailure(
            MailException exception) {
        // Never return raw exceptions or SMTP credentials to the client.
        return ResponseEntity.status(
                HttpStatus.BAD_GATEWAY)
                .body("SMTP submission was not confirmed");
    }
}
~~~

This is solely an **illustrative error mapper**. `502 Bad Gateway` is used here because the local API sits in front of an SMTP service; a production API may choose another status per its contract. The phrase "not confirmed" intentionally **does not claim "definitely not sent"**.

When a production API supports retries and outcomes can be uncertain, you need a job ID, idempotency key, durably persisted state, and a query/reconciliation path; do not simply return 502 and let the client retry unconditionally.

### 12.2. Do Not Retry Every Failure the Same Way

- Invalid credentials: fix configuration instead of retrying hundreds of times per second.
- Untrusted certificate: fix CA/hostname/TLS rather than enabling trust-all.
- Temporary SMTP 4xx: retry with exponential backoff and jitter.
- Permanently rejected recipient: do not retry indefinitely.
- Timeout after submission: treat as a potentially uncertain outcome.

Retry rules belong in a durable orchestration layer once the application needs reliability, not in an infinite loop inside an HTTP request.

### 12.3. Distinguishing SUBMITTED from DELIVERED

~~~text
JavaMailSender.send(message) returns normally
      |
      v
SMTP relay accepted the submission
      |
      v
Provider processing
      |
      +-- delivered to downstream mail server
      +-- deferred
      +-- bounced
      +-- filtered/rejected later
~~~

Therefore, the demo response `SUBMITTED_TO_SMTP` only marks the transport call milestone; **it does not guarantee Inbox delivery**. Observing delivery, bounces, or complaints requires provider events or mail infrastructure supporting the appropriate contract.

## 13. Sending Vietnamese Text and Charset Handling

Plain text can contain Unicode:

~~~java
String subject = "Xác nhận đăng ký thành công";
String body =
        "Xin chào,\n"
        + "Tài khoản của bạn đã được kích hoạt.\n"
        + "Trân trọng.";

mailService.sendPlainText(
        new PlainTextMailCommand(
                "learner@example.net",
                subject,
                body));
~~~

`SimpleMailMessage` holds Java `String` values. `JavaMailSenderImpl` and Jakarta Mail prepare MIME headers and body; setting `spring.mail.default-encoding=UTF-8` configures the application's default charset.

### 13.1. When Vietnamese Text Breaks

Check end-to-end:

1. Java/YAML files are saved as UTF-8.
2. HTTP request bodies declare and send the proper charset.
3. The request DTO receives an intact Java `String` (no `?` or mojibake at intake).
4. `spring.mail.default-encoding` is set properly.
5. The SMTP test mailbox decodes the MIME charset properly.
6. The final mail client handles standard MIME correctly.

Never "fix" broken text by repeatedly converting a String to bytes and back under a different charset. That often corrupts data before the sender even sees it.

### 13.2. Multi-Line Text Blocks

With Java 17:

~~~java
String body = """
        Xin chào,

        Tài khoản của bạn đã được kích hoạt.
        Nếu cần trợ giúp, vui lòng liên hệ hỗ trợ.

        Trân trọng,
        Đội ngũ hỗ trợ
        """;
~~~

Text blocks keep the body readable. Inspect actual newlines and indentation because Java text blocks follow specific whitespace rules. Plain-text emails can use blank lines, bullets, or URLs, but they do not support buttons or HTML formatting.

## 14. Extending with Cc, Bcc, and Reply-To

When additional recipients are needed, `SimpleMailMessage` supports:

~~~java
SimpleMailMessage message = new SimpleMailMessage();

message.setFrom("no-reply@example.test");
message.setTo("customer@example.net");
message.setCc("team@example.net");
message.setBcc("audit@example.net");
message.setReplyTo("support@example.test");
message.setSubject("Order update");
message.setText(
        "Hello,\nYour order has been confirmed.");

javaMailSender.send(message);
~~~

Where:

- `To` holds primary recipients.
- `Cc` is generally visible to other recipients.
- `Bcc` sends to recipients hidden from the regular recipient list; never use it as an arbitrary bulk-mail mechanism.
- `Reply-To` tells the mail client which address to use when the user replies, which can differ from `From`.

### 14.1. Still Must Validate and Authorize

If a controller accepts arbitrary `Cc`, `Bcc`, or `Reply-To`, enforce sending permissions, allowlists, recipient count caps, and header validation. Never mix addresses from different tenants into the same email, as that leaks personal data.

### 14.2. Multi-Recipient and Partial Success

A message with multiple `To`/`Cc`/`Bcc` recipients may be accepted by the SMTP server for some recipients and rejected for others. If you retry the entire message, already-accepted recipients risk receiving duplicates.

When per-recipient delivery/bounce tracking is required, a **one logical job per recipient** model or a recipient-outcome table is usually much easier to control.

### 14.3. Do Not Put HTML in setText

`message.setText("<strong>Hello</strong>")` is still plain text. When HTML, attachments, inline logos, or `multipart/alternative` are needed, switch to `MimeMessageHelper`. Never try to hack custom MIME headers onto `SimpleMailMessage` to turn it into an HTML message.

## 15. Limitations of Synchronous Sending

With the current implementation:

~~~text
HTTP request
   -> LocalMailController
      -> MailService
         -> JavaMailSender.send(...)
   -> HTTP response after transport returns
~~~

This fits learning or small internal tools, yet carries risks in production:

- Slow SMTP increases HTTP latency.
- Provider outages directly disrupt business requests.
- Client timeouts and retries can send duplicates.
- Many concurrent requests tie up threads and network resources.
- Process crashes lose requests lacking a persistent record.

### 15.1. Avoid Sending Directly Inside a Business Transaction

Example:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    orderRepository.confirm(orderId);
    mailService.sendPlainText(
            new PlainTextMailCommand(
                    "customer@example.net",
                    "Order confirmed",
                    "Thank you for your order."));
}
~~~

SMTP does not participate in database transactions. If SMTP accepts and the DB rolls back, the email is still sent; if the DB commits and the process dies before sending, the email is lost.

When requests must not be lost, use a **transactional outbox**:

~~~mermaid
flowchart LR
    A["Business event"] --> B["DB transaction"]
    B --> C["Business data"]
    B --> D["Mail outbox PENDING"]
    D --> E["Background worker"]
    E --> F["MailService"]
    F --> G["SMTP relay"]
~~~

Inside the same business DB transaction, write `mail_outbox` alongside the business update. After commit, a worker picks up the job, invokes this service, and records retries and state. If the outbox and business data reside in different databases, a dedicated atomicity architecture is needed; plain `@Transactional` will not synchronize two separate stores.

### 15.2. Message Keys and Idempotency

If an event is redelivered:

~~~text
OrderConfirmed(eventId=evt-123)
   -> messageKey=order-confirmation:evt-123:recipient-9
~~~

preserve the exact same message key across every redelivery. The database can enforce `UNIQUE(tenant_id, message_key)` to avoid creating duplicate logical mail jobs.

However, **a unique key does not guarantee exactly-once SMTP**: a worker may crash after the SMTP server accepts the message but before committing the `SUBMITTED` state. Retrying may still cause the server to receive two emails. Attempt tracking, `UNKNOWN` handling/reconciliation, and per-mail-type policies are required.

### 15.3. Scheduler and Retries

An outbox worker can store:

~~~text
jobId
messageKey
mailType
recipient
payloadRef
state=PENDING|RETRY_WAIT|SUBMITTED|FAILED_FINAL|UNKNOWN
scheduledAt
nextAttemptAt
attemptCount
~~~

Workers claim due jobs using controlled locks/leases, call the service, and persist the outcome. Temporary 4xx errors can be retried with backoff; credential or TLS misconfigurations usually require alerts and root-cause fixes; expired OTP jobs should not be sent after an outage.

This is an **architectural extension**, not something `SimpleMailMessage` provides on its own.

## 16. Securing MailService in Real Applications

An email-sending service is a capability that can be abused if permissions are not restricted.

### 16.1. Preventing Open Relays

A public API like:

~~~http
POST /api/mail
{"to":"anyone@example.net","subject":"...","body":"..."}
~~~

without authentication and rate limits can be exploited to send spam, phishing, or exhaust quotas. In this lesson, the controller is restricted to the `local` profile. In real deployments:

- authenticate callers;
- authorize mail type, tenant, and sender profile;
- enforce recipient controls and destination policies;
- rate-limit by principal, tenant, and use case;
- bound request payload sizes;
- record minimal audit trails;
- use idempotency when requests may be retried;
- never let callers change `From` or `Reply-To` outside authorized addresses.

### 16.2. Protecting SMTP Credentials

Never write:

~~~yaml
spring:
  mail:
    username: real-smtp-user
    password: real-smtp-password
~~~

in a repository. Fetch credentials from a secret manager or secure injection mechanism, restrict secret access, and maintain a rotation process. Never print passwords into exception logs or debug transcripts.

### 16.3. Keep TLS Verification Enabled

With real SMTP providers, use the exact host, port, and TLS mode and verify both certificate chains and hostnames. Never set `mail.smtp.ssl.trust=*` or use a trust-all manager to silence `PKIX path building failed`.

Plaintext on loopback in a local sandbox is an isolated learning case, **not** a precedent for using plaintext in production.

### 16.4. Never Log Bodies or Tokens

Emails may contain:

- OTPs;
- password-reset tokens;
- invoice/order details;
- recipient addresses;
- account details.

Logs should contain only necessary metadata such as mail type, sender profile, correlation ID, error class, and access-controlled status. Never use recipient address, subject, body, or token as metric labels.

## 17. Observability and Metrics

When integrating into high-request environments, instrument metrics such as:

| Suggested Metric | Meaning |
| --- | --- |
| `mail_submission_attempts_total` | Count of SMTP/API calls |
| `mail_submission_duration_seconds` | Duration of one attempt |
| `mail_submission_errors_total` | Transport errors by category |
| `mail_jobs_created_total` | Logical jobs if using an outbox |
| `mail_outbox_pending` | Number of pending jobs |
| `mail_outbox_oldest_pending_age_seconds` | Backlog age |
| `mail_retry_scheduled_total` | Scheduled retries |

These are suggested application-instrumented metric names; `spring-boot-starter-mail` does not emit all of them automatically.

### 17.1. Count the Right Units

~~~text
1 logical mail job
3 SMTP attempts
1 accepted submission
~~~

Job count is 1, attempts is 3, and accepted submission is 1. Never label a normal return from `JavaMailSender.send(...)` as `delivered`.

### 17.2. Keep Label Cardinality Bounded

Safe labels include:

~~~text
sender_profile=tx_primary|tx_backup
mail_type=order_confirmation|otp|invoice|newsletter
result=submitted|exception
error_class=auth|tls|network|recipient|unknown
~~~

Never use `recipient`, `messageKey`, `subject`, or raw exception text as metric labels.

### 17.3. Essential Alerts

- Continuous spike in authentication failures.
- TLS handshake errors after certificate rotation.
- SMTP timeouts growing the backlog.
- Provider throttling driving high retry counts.
- Critical mail types such as OTPs exceeding wait thresholds.
- Sudden traffic spikes indicating possible abuse.

Alerts should use contextual metrics and thresholds; do not page engineers just because a single test request failed.

## 18. Common Troubleshooting Table

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Cannot inject `JavaMailSender` | Missing starter, unconfigured host, or wrong profile | Check dependencies and active profile |
| `Connection refused` | SMTP sandbox not running, wrong port, or network issue | Verify host/port from where the app runs |
| `Connect timed out` | Firewall, routing, or wrong host | Check TCP connectivity |
| `MailAuthenticationException` | Credentials/OAuth or SMTP AUTH policy | Check account and auth mechanism |
| `535 Authentication failed` | Provider rejected credentials | Fix credentials/policy; never disable TLS |
| `PKIX path building failed` | JVM does not trust CA chain | Fix truststore/chain/hostname |
| Hostname mismatch | Certificate SAN does not match SMTP host | Use valid endpoint/certificate |
| STARTTLS required but unsupported | Wrong host/port/proxy | Select the proper SMTP endpoint |
| `Unsupported or unrecognized SSL message` | Mismatched implicit TLS vs. STARTTLS mode | Distinguish port 465 vs. 587 |
| SMTP `550/553` | From or recipient rejected per provider policy | Verify sender identity/recipient |
| Broken Vietnamese body | Inconsistent encoding | Check UTF-8 and MIME charset |
| Raw HTML tags displayed | Used `SimpleMailMessage` for HTML | Switch to `MimeMessageHelper` |
| API 404 in prod | `LocalMailController` enabled only in local | By design; never enable local in prod |
| API 400 | DTO/command validation failed | Fix the request |
| Email sent but not in Inbox | Provider filtering/delivery/bounce | Track delivery events; do not infer from submission |

### 18.1. A Common Cause: localhost Inside Containers

If Mailpit runs in container A and Spring Boot runs in container B, `127.0.0.1` inside B does not point to A. Use a shared Docker network and the appropriate service hostname. Avoid abusing host networking or exposing SMTP ports publicly just to clear connection errors.

### 18.2. Do Not Ignore Root Causes

`MailSendException` can wrap `MessagingException`, `SocketException`, or `SSLHandshakeException`. Inspect the nested cause to distinguish auth, TLS, network, and message errors; never blindly retry every error with the same policy.

## 19. Extended Practice Exercises

### Exercise 1: Send Multi-Line Vietnamese Content

Write an email with subject and body:

~~~text
Subject: Thông báo kích hoạt tài khoản

Xin chào,

Tài khoản của bạn đã được kích hoạt thành công.
Bạn có thể đăng nhập và bắt đầu sử dụng dịch vụ.

Trân trọng,
Đội ngũ hỗ trợ
~~~

Inspect in Mailpit to confirm Vietnamese diacritics, line breaks, and subject render properly.

### Exercise 2: Add Reply-To via Configuration

Add `app.mail.reply-to`, inject it into the service, and invoke `message.setReplyTo(...)` when authorized. Assert with Mockito `getReplyTo()`. Never allow clients to supply an arbitrary value.

### Exercise 3: Send Cc and Bcc

Extend the command to accept validated and authorized secondary recipients. Use `setCc(...)` and `setBcc(...)`, and capture the message in a unit test. Consider privacy and partial SMTP acceptance before using multi-recipient sends in production.

### Exercise 4: Reject Subjects with CR/LF

Try sending a subject:

~~~text
Hello\r\nBcc: hidden@example.org
~~~

Expect the constructor to reject it without calling SMTP. The body should still allow newlines.

### Exercise 5: Simulate an SMTP Outage

Stop Mailpit, call the service, and observe `MailException`. Never let the API return `SUBMITTED_TO_SMTP` when the transport call fails. Verify logs contain no credentials or sensitive content.

### Exercise 6: Two Consecutive Sends

Send to two different recipients within the same test. Capture both messages and verify `To`, `Subject`, and `Text` do not mix and that both are distinct object instances.

### Exercise 7: Design an Outbox Instead of Synchronous Sending

Create a `mail_outbox` table with `id`, `message_key`, `recipient`, `payload_ref`, `status`, `attempt_count`, and `next_attempt_at`. Write to the outbox inside the business transaction, have a worker claim/schedule attempts and call `MailService`, and add a unique constraint so broker redeliveries do not create duplicate logical jobs.

### Exercise 8: Upgrade to HTML with MimeMessageHelper

Try `setText("<h1>Hello</h1>")` and observe the literal markup in plain text. Then build a separate service using `MimeMessageHelper` with proper `text/plain` and `text/html` MIME parts rather than cramming every format into the existing class.

## 20. Mistakes to Avoid

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Creating `JavaMailSenderImpl` in every business method | Duplicated config, hard to test | Inject the bean |
| Sharing a mutable `SimpleMailMessage` | Cross-contaminated recipients | Instantiate a new one each time |
| Hardcoding SMTP password | Secret exposure | Env vars / secret manager |
| Letting requests set arbitrary `From` | Spoofing / provider rejection | Server-controlled sender |
| Using `setText` for HTML | Literal markup displayed | `MimeMessageHelper` |
| Skipping recipient/subject/body validation | Bad input, late errors | Command + Bean Validation |
| Only `@Email` without authorization | API abused for spam | Auth, quota, rate limiting |
| Exposing local controller publicly | Open relay | Profile + network isolation |
| Missing network timeouts | Threads hang indefinitely | Timeout properties |
| Port 587 configured with implicit TLS | Handshake failure | Proper STARTTLS |
| Disabling TLS verification after PKIX errors | Loses server authentication | Fix CA/chain/hostname |
| Catching exception and returning normally | Caller assumes sent | Explicit error contract |
| Treating completed `send` as delivered | Inaccurate reporting | Separate submitted from delivered |
| Retrying every timeout immediately | Risk of duplicates | `UNKNOWN` handling / reconciliation |
| Sending inside business DB transaction | Not atomic with SMTP | Transactional outbox |
| Logging full message/body/OTP | Data leakage | Minimal metadata |
| Using real SMTP in unit tests | Flaky tests and unintended sends | Mockito mocks |

## 21. End-to-End Scenario: Account Activated Notification

Suppose a business workflow has verified an account:

~~~text
Business event: ACCOUNT_ACTIVATED
Account ID: user-123
Recipient: learner@example.net
~~~

The application constructs a command:

~~~java
PlainTextMailCommand command =
        new PlainTextMailCommand(
                "learner@example.net",
                "Account activated",
                """
                Hello,

                Your account has been activated.
                You can now sign in and use the service.

                Best regards,
                Support Team
                """);

mailService.sendPlainText(command);
~~~

In a local environment:

~~~text
ACCOUNT_ACTIVATED
    -> PlainTextMailCommand
    -> SmtpPlainTextMailService
    -> new SimpleMailMessage()
    -> setFrom / setTo / setSubject / setText
    -> JavaMailSender.send()
    -> Mailpit
    -> learner inspects sandbox inbox
~~~

In production when requests must never be lost:

~~~text
ACCOUNT_ACTIVATED persisted
    -> durable mail outbox with message key
    -> worker
    -> SmtpPlainTextMailService
    -> SMTP relay
    -> provider delivery/bounce events
~~~

The message key can derive from `accountActivatedEventId`, mail type, and recipient ID, backed by a DB unique constraint. Worker retries do not create a new logical job, though uncertainty still needs handling if SMTP accepted right before a process crash.

## 22. Lesson Completion Checklist

### Configuration

- [ ] `spring-boot-starter-mail` and test dependencies added.
- [ ] Local profile configured with an SMTP sandbox.
- [ ] Production profile configured with proper SMTP TLS and auth.
- [ ] `app.mail.from` explicitly configured and authorized by the provider.
- [ ] No hardcoded secrets or disabled TLS verification.
- [ ] Connection, read, and write timeouts configured.

### MailService Implementation

- [ ] `MailService` interface defined.
- [ ] Immutable `PlainTextMailCommand` defined.
- [ ] `SmtpPlainTextMailService` injects `JavaMailSender`.
- [ ] Fresh `SimpleMailMessage` created for every send.
- [ ] `From`, `To`, `Subject`, and `Text` set accurately.
- [ ] `SimpleMailMessage` not misused as an HTML/attachment API.
- [ ] `MailException` not swallowed.

### Testing

- [ ] Mockito unit tests verify `From`/`To`/`Subject`/`Text`.
- [ ] Exception propagation tested.
- [ ] Command rejection of CR/LF in subjects tested.
- [ ] Test emails verified in local sandbox without sending to the Internet.
- [ ] Unicode and newlines verified in the test mailbox.
- [ ] Demo controller restricted to `local` and never exposed in production.

### Readiness to Scale

- [ ] Distinction between SMTP submitted and provider delivered understood.
- [ ] Authorization and rate limiting planned if exposing a real API.
- [ ] Clear understanding of when `MimeMessageHelper` is required.
- [ ] Clear understanding of why outbox/idempotency is needed when emails must not be lost.
- [ ] Monitoring and retry policies defined for SMTP failures.

## 23. Summary

The key takeaway of this lesson is turning repetitive text-email code into a clean, reusable service:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom(fromAddress);
message.setTo(command.to());
message.setSubject(command.subject());
message.setText(command.body());
javaMailSender.send(message);
~~~

**`SimpleMailMessage` is the right choice for simple plain-text emails**. `JavaMailSender` provides the SMTP transport layer; Spring Boot handles configuration via `spring.mail.*`; a clean command and interface keep business code tidy; and Mockito plus an SMTP sandbox let you verify behavior without real email accounts.

Crucially, do not stop at "calling `send(...)` without throwing an error". Real systems must control `From`, recipients, credentials, TLS, quotas, timeouts, and state semantics. **SMTP submission does not mean delivered**, and synchronous sending inside a business transaction neither prevents message loss nor guards against duplicates. As requirements grow, you can keep this service as the transport adapter and add an outbox, message keys, retries, and tracking at the appropriate layers.

### References

- **Spring Framework Reference — Email:** `MailSender`, `JavaMailSender`, and `SimpleMailMessage`.
- **Spring Framework API — SimpleMailMessage:** `setFrom`, `setTo`, `setCc`, `setBcc`, `setReplyTo`, `setSubject`, `setText`.
- **Spring Framework API — JavaMailSender:** `send(SimpleMailMessage)`, `send(MimeMessage)`.
- **Spring Boot Reference — Sending Email:** `spring-boot-starter-mail`, `spring.mail.*`, and mail auto-configuration.
- **Spring Boot Reference — Profiles:** `application-local.yml`, `application-prod.yml`, and profile activation.
- **Jakarta Mail API:** SMTP transport, MIME encoding, and exceptions.
- **Jakarta Bean Validation:** `@Valid`, `@Email`, `@NotBlank`, `@Size`.
- **JUnit 5 / Mockito Documentation:** `@ExtendWith`, `@Mock`, `ArgumentCaptor`, and `verify`.
- **Mailpit Documentation:** SMTP sandbox, web UI, and Docker configuration.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP transactions and submission responses.
- **RFC 5322 — Internet Message Format:** `From`, `To`, `Subject`, and email headers.
