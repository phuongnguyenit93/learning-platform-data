# Creating HTML and Plain-Text Emails with MimeMessageHelper

A transactional email sent from Spring Framework Mail should not consist of only an HTML snippet. Many email clients prefer rendering HTML, yet corporate environments, lightweight mail readers, accessibility screen readers, testing tools, and automated processors rely on a **plain-text** version. An email carrying both versions is typically packaged as **MIME `multipart/alternative`**: one message with two representations of the same content, not two separate emails.

In this practice project, we build a Spring Boot application that sends an **order confirmation email** with:

- A readable, complete `text/plain` version.
- A well-formatted `text/html` version with a link to the order.
- `MimeMessageHelper#setText(plainText, htmlText)` to construct a proper MIME alternative.
- UTF-8 to preserve Vietnamese characters in the subject, body, and display name.
- Thymeleaf to render HTML from dynamic data with proper escaping.
- Mailpit as a local SMTP server to inspect content **without sending real emails**.
- An API enabled only under the `local` profile, avoiding accidentally creating an open relay upon deployment.
- Tests that inspect actual MIME content and distinguish SMTP submission from delivery.

This is a **complete practice project focused on email content**. Production concerns such as a transactional outbox, API authentication, rate quotas, and provider events are placed at the appropriate architectural boundaries rather than pretending they come for free simply by calling `JavaMailSender`.

## 1. Learning Goals

Upon completion, you will be able to:

1. Understand why HTML and plain text belong inside the same email.
2. Distinguish Spring `SimpleMailMessage`, Jakarta `MimeMessage`, `JavaMailSender`, and `MimeMessageHelper`.
3. Set up a Spring Boot Maven structure with Mail, Web, Validation, and Thymeleaf.
4. Start an SMTP catcher to receive emails locally.
5. Author two content versions from the same order data.
6. Build a `MimeMessage` with `From`, `To`, `Reply-To`, `Subject`, and charset.
7. Call the `setText(plainText, htmlText)` overload correctly.
8. Verify that MIME contains both `text/plain` and `text/html`.
9. Understand why the top-level `Content-Type` may be `multipart/mixed`.
10. Test Vietnamese text, HTML escaping, URLs, and SMTP connection failures.
11. Separate the synchronous demo from a durable production architecture.

## 2. Expected Outcome

Send an example request payload:

```json
{
  "to": "buyer@example.test",
  "customerName": "Nguyễn An",
  "orderCode": "ORD-2026-001"
}
```

Corresponding plain-text version:

```text
Xin chào Nguyễn An,

Đơn hàng ORD-2026-001 của bạn đã được ghi nhận.

Xem đơn hàng: http://localhost:8080/orders/ORD-2026-001

Đây là email tự động. Nếu cần hỗ trợ, hãy phản hồi email này.

Trân trọng,
Demo Workspace
```

Semantically equivalent HTML version:

```html
<h1>Xác nhận đơn hàng</h1>
<p>Xin chào <strong>Nguyễn An</strong>,</p>
<p>Đơn hàng <strong>ORD-2026-001</strong> đã được ghi nhận.</p>
<a href="http://localhost:8080/orders/ORD-2026-001">
  Xem đơn hàng
</a>
```

Both parts must carry the same essential information: a recipient must never lose the order code or link just because their client renders plain text.

When opening the email in Mailpit, the UI normally lets you view the HTML part, the plain-text part, and the MIME source. This is **one email containing two versions**, not the application sending twice.

## 3. Practice Flow Diagram

```text
POST /api/dev/order-confirmations
              |
              v
      @Valid OrderMailRequest
              |
              v
      OrderMailRenderer
        |           |
        |           +--> Thymeleaf HTML template
        |
        +--> Plain text renderer
              |
              v
      RenderedMail
        - subject
        - plainText
        - htmlText
              |
              v
      OrderMailService
        - JavaMailSender.createMimeMessage()
        - MimeMessageHelper(..., UTF-8)
        - setFrom / setTo / setReplyTo
        - setSubject
        - setText(plainText, htmlText)
              |
              v
      JavaMailSender.send(...)
              |
              v
      Mailpit SMTP :1025
              |
              v
      Mailpit UI :8025
```

`OrderMailRequest`, `RenderedMail`, `OrderMailRenderer`, and `OrderMailService` are classes we build ourselves. `JavaMailSender` and `MimeMessageHelper` are Spring Framework Mail APIs.

## 4. Prerequisites

- JDK 17 or later with a compatible Spring Boot version.
- Maven and an IDE supporting Java/Spring.
- Docker/Compose if running Mailpit in a container.
- No Gmail or production SMTP account needed.
- A browser to inspect Mailpit at `http://localhost:8025`.
- An HTTP client such as `curl`, Postman, or PowerShell.

The examples below pick **Spring Boot 3.5.0** as the illustrative Maven version, corresponding to the Jakarta `jakarta.mail.*` ecosystem. A project can use whichever Spring Boot version your organization supports; do not treat the version in this guide as a claim of "latest".

If a project uses Spring Boot 2 / Spring Framework 5, the mail namespace is `javax.mail.*`; never mix both namespaces in the same codebase.

## 5. Directory Structure

```text
mail-html-plain-demo/
├── pom.xml
├── compose.yml
└── src/
    ├── main/
    │   ├── java/com/example/maildemo/
    │   │   ├── MailDemoApplication.java
    │   │   ├── config/
    │   │   │   └── DemoMailProperties.java
    │   │   └── mail/
    │   │       ├── OrderMailRequest.java
    │   │       ├── RenderedMail.java
    │   │       ├── OrderMailRenderer.java
    │   │       ├── OrderMailService.java
    │   │       ├── SubmissionReceipt.java
    │   │       ├── MailPreparationFailure.java
    │   │       ├── MailSubmissionFailure.java
    │   │       ├── MailDemoController.java
    │   │       └── MailDemoErrorHandler.java
    │   └── resources/
    │       ├── application-local.yml
    │       └── templates/mail/
    │           └── order-confirmation.html
    └── test/
        └── java/com/example/maildemo/mail/
            └── OrderMailServiceTest.java
```

We will build in order from the local environment to the renderer, sending service, and tests. Each illustrative file below represents content for the **guided project you create**, not an instruction to edit unrelated files in the module you are reading.

## 6. Initializing Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mail-html-plain-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>mail-html-plain-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Role of dependencies:**

| Dependency | Purpose |
| --- | --- |
| `spring-boot-starter-mail` | Configures `JavaMailSender` and Jakarta Mail transport |
| `spring-boot-starter-web` | Dev API to trigger test sends |
| `spring-boot-starter-validation` | Bean Validation for requests and properties |
| `spring-boot-starter-thymeleaf` | Renders HTML templates with `th:text`, `th:href` |
| `spring-boot-starter-test` | JUnit, Mockito, Spring Test per dependency management |

You do not need to manually add `javax.mail` or `jakarta.mail-api` versions alongside this starter. Rely on Spring Boot dependency management to avoid JavaMail provider/API version mismatches.

## 7. Running an SMTP Catcher with Mailpit

Create `compose.yml`:

```yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "127.0.0.1:1025:1025"
      - "127.0.0.1:8025:8025"
```

Start it in the project directory:

```bash
docker compose up -d
```

Access:

```text
SMTP server : localhost:1025
Mailpit UI  : http://localhost:8025
```

Mailpit captures emails sent by the application and displays them for inspection; it **never forwards emails to real mailboxes** in this local setup.

Notes:

- `127.0.0.1` in port bindings exposes ports only to the local machine.
- Never deploy an unauthenticated Mailpit catcher configuration to the Internet.
- Image tag `latest` is convenient for lessons; CI and production-like team tests should pin a version or digest.
- If the app runs in a container on the same Compose network, the SMTP host is typically the service name `mailpit`, not the app container's `localhost`.
- If Docker is unavailable, any other SMTP capture tool works for the same purpose.

## 8. Configuring application-local.yml

Create `src/main/resources/application-local.yml`:

```yaml
server:
  port: 8080

spring:
  mail:
    host: localhost
    port: 1025
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
      "[mail.debug]": false

  thymeleaf:
    cache: false
    encoding: UTF-8

demo:
  mail:
    from: "no-reply@example.test"
    from-name: "Demo Workspace"
    reply-to: "support@example.test"
    public-base-url: "http://localhost:8080"
```

Locally, Mailpit on port 1025 does not require SMTP AUTH/TLS in the demo configuration. **Never carry `auth=false` or `starttls=false` over to a production provider** that requires authentication and encryption.

For production SMTP on port 587, you normally configure authentication, STARTTLS, certificate/hostname verification, and secrets pulled from environment variables or a secret manager. Never hardcode SMTP passwords in a repository.

`demo.mail.*` properties are **application configuration**; Spring Boot does not know what sender or from-name means unless we bind them to a configuration class.

## 9. Main Application and Configuration Properties

`MailDemoApplication.java`:

```java
package com.example.maildemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MailDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MailDemoApplication.class, args);
    }
}
```

`config/DemoMailProperties.java`:

```java
package com.example.maildemo.config;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.mail")
public record DemoMailProperties(
    @NotBlank @Email String from,
    @NotBlank String fromName,
    @NotBlank @Email String replyTo,
    @NotBlank String publicBaseUrl
) {}
```

Spring Boot binds `from-name` to `fromName` and `public-base-url` to `publicBaseUrl` via relaxed binding.

In production, validate that `publicBaseUrl` is an HTTPS URL on an allowlisted domain; never let an HTTP request pass an arbitrary URL to embed in an email, as that enables phishing. The local example uses HTTP and `localhost` strictly for practice.

`@ConfigurationPropertiesScan` and `@Validated` catch misconfigurations early. For more complex production setups, add validators for URLs and sender domains.

## 10. DTO for Email Input Data

Create `mail/OrderMailRequest.java`:

```java
package com.example.maildemo.mail;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record OrderMailRequest(
    @NotBlank @Email String to,

    @NotBlank @Size(max = 80) String customerName,

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,40}")
    String orderCode
) {}
```

Key points:

- `@Email` checks format at the validation level; it does not prove the address belongs to the right recipient.
- `@NotBlank` prevents empty addresses or text.
- `@Size` prevents overly long fields beyond notification needs.
- `@Pattern` restricts the order code to a relatively safe path segment in this example.
- Do not accept `from`, `replyTo`, or SMTP credentials from the request body.
- Do not let clients supply raw HTML/templates, which would turn the API into an open relay.

**In production, a controller should not let arbitrary users pass `to` and freely trigger mail sending.** The recipient should be resolved from an order/account the caller is authorized to access. This endpoint is enabled only under the `local` profile.

## 11. Model for Both Content Versions

Create `mail/RenderedMail.java`:

```java
package com.example.maildemo.mail;

public record RenderedMail(
    String subject,
    String plainText,
    String htmlText
) {}
```

This model represents **rendered content**, without transport settings and before constructing a Jakarta `MimeMessage`.

It separates responsibilities:

```text
OrderMailRequest
     |
     v
Content renderer
     |
     +--> subject
     +--> plainText
     +--> htmlText
     |
     v
MimeMessage construction
     |
     v
SMTP transport
```

Benefits:

- Plain text and HTML can be unit-tested without SMTP.
- One dataset generates two consistent versions.
- Templates can be versioned.
- Rendering errors are separated from SMTP errors.
- No business formatting logic leaks into the SMTP handler.

Never log the full `RenderedMail` because `record.toString()` may contain the entire message body, customer name, order code, and links.

## 12. Writing the HTML Template with Thymeleaf

Create `src/main/resources/templates/mail/order-confirmation.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Xác nhận đơn hàng</title>
</head>
<body style="margin:0;padding:0;background:#f4f6fa;font-family:Arial,sans-serif;">
<table role="presentation" cellpadding="0" cellspacing="0"
       style="width:100%;background:#f4f6fa;padding:24px;">
    <tr>
        <td align="center">
            <table role="presentation" cellpadding="0" cellspacing="0"
                   style="width:100%;max-width:600px;background:#ffffff;
                          border:1px solid #e4e7ec;border-radius:8px;">
                <tr>
                    <td style="padding:28px;">
                        <h1 style="margin:0 0 16px;color:#17202a;
                                   font-size:24px;">
                            Xác nhận đơn hàng
                        </h1>

                        <p style="font-size:16px;line-height:1.6;color:#263445;">
                            Xin chào
                            <strong th:text="${customerName}">Khách hàng</strong>,
                        </p>

                        <p style="font-size:16px;line-height:1.6;color:#263445;">
                            Đơn hàng
                            <strong th:text="${orderCode}">ORD-DEMO</strong>
                            của bạn đã được ghi nhận.
                        </p>

                        <p style="padding:16px 0;">
                            <a th:href="${orderUrl}"
                               href="http://localhost:8080/orders/ORD-DEMO"
                               style="background:#2255cc;color:#ffffff;
                                      text-decoration:none;padding:12px 18px;
                                      border-radius:6px;display:inline-block;">
                                Xem đơn hàng
                            </a>
                        </p>

                        <p style="font-size:13px;line-height:1.6;color:#667085;">
                            Đây là email tự động. Nếu cần hỗ trợ,
                            hãy phản hồi email này.
                        </p>

                        <p style="font-size:14px;color:#667085;">
                            Trân trọng,
                            <strong>Demo Workspace</strong>
                        </p>
                    </td>
                </tr>
            </table>
        </td>
    </tr>
</table>
</body>
</html>
```

The `th:text="${customerName}"` and `th:text="${orderCode}"` expressions instruct Thymeleaf to escape values in an HTML text context. Avoid replacing this with manual HTML string concatenation and `th:utext` on client-supplied input.

`th:href="${orderUrl}"` inserts the URL into an HTML attribute with escaping. **Escaping alone does not guarantee a safe URL**: the source generating `orderUrl` must still belong to an allowed domain, avoiding `javascript:`, user-controlled redirects, or phishing links. In the demo, the base URL is server-side config and `orderCode` is constrained by regex.

Email clients support CSS/HTML inconsistently. The example uses tables, inline styles, and relatively simple markup, avoiding JavaScript, complex CSS layouts, or remote fonts.

## 13. Why Not Use Web-Page-Style HTML?

Email HTML differs from browser HTML:

- Many email clients strip JavaScript completely.
- CSS support can be limited; inline CSS is generally more reliable than advanced stylesheets.
- Remote images may be blocked by default.
- Table-based layouts often have broader compatibility than modern layout techniques.
- Media queries and dark mode vary widely in support.
- Forms, iframes, and scripts are generally untrusted in email.
- Links may pass through security scanners or provider rewriting.
- Some clients display plain text instead of HTML.

Therefore, this project produces **deliberately simple HTML** while still providing a complete plain-text version. Never treat the plain version as an afterthought that needs no verification.

## 14. Rendering HTML and Plain Text from the Same Data

Create `mail/OrderMailRenderer.java`:

```java
package com.example.maildemo.mail;

import java.util.Locale;

import com.example.maildemo.config.DemoMailProperties;
import org.springframework.stereotype.Component;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Component
public class OrderMailRenderer {

    private final TemplateEngine templateEngine;
    private final DemoMailProperties mailProperties;

    public OrderMailRenderer(
            TemplateEngine templateEngine,
            DemoMailProperties mailProperties) {
        this.templateEngine = templateEngine;
        this.mailProperties = mailProperties;
    }

    public RenderedMail render(OrderMailRequest request) {
        String orderUrl =
            mailProperties.publicBaseUrl().replaceAll("/+$", "")
                + "/orders/" + request.orderCode();

        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("customerName", request.customerName());
        context.setVariable("orderCode", request.orderCode());
        context.setVariable("orderUrl", orderUrl);

        String html = templateEngine.process(
            "mail/order-confirmation", context
        );

        String safeName = request.customerName()
            .replace('\r', ' ')
            .replace('\n', ' ')
            .trim();

        String plain = """
            Xin chào %s,

            Đơn hàng %s của bạn đã được ghi nhận.

            Xem đơn hàng: %s

            Đây là email tự động. Nếu cần hỗ trợ,
            hãy phản hồi email này.

            Trân trọng,
            Demo Workspace
            """.formatted(safeName, request.orderCode(), orderUrl);

        String subject =
            "Xác nhận đơn hàng " + request.orderCode();

        return new RenderedMail(subject, plain, html);
    }
}
```

Key takeaways:

1. **The same `OrderMailRequest`** feeds subject, plain text, and HTML.
2. `templateEngine.process(...)` resolves the template via Spring Boot's Thymeleaf resolver.
3. Plain text includes clean blank lines, order code, and full URL.
4. `safeName` replaces CR/LF with spaces so user input cannot inject extra lines in the illustrative text output.
5. `orderCode` is regex-validated so slashes or URL schemes cannot enter the path.
6. `publicBaseUrl` is configured server-side; real products should enforce HTTPS and allowed domains.
7. The renderer knows nothing about SMTP hosts, passwords, or providers.

Do not run `HtmlUtils.htmlEscape` before passing values to `th:text`: that double-escapes `&` or `<`. Let the template engine perform escaping for its output context.

### Mini Exercise

Try replacing `customerName` locally with synthetic input containing `&`, quotes, or `<b>An</b>`. The HTML output should render **literal user text**, not execute user-supplied markup. The plain-text version may retain literal `<` and `>` because it is text, not HTML.

## 15. Creating a Receipt for Submission

Create `mail/SubmissionReceipt.java`:

```java
package com.example.maildemo.mail;

import java.util.UUID;

public record SubmissionReceipt(
    UUID notificationId,
    String submissionStatus
) {}
```

In the demo, `SUBMITTED` means Spring Mail reported no error when submitting to the SMTP catcher. **Do not call this status `DELIVERED`**, since delivery comes from downstream delivery/provider events.

The UUID in the demo helps correlate responses and logs. In production, generate a durable ID in the database/outbox before SMTP; an in-memory UUID alone is not proof of a persisted notification.

## 16. Exceptions for Preparation and Submission Boundaries

Create `mail/MailPreparationFailure.java`:

```java
package com.example.maildemo.mail;

public class MailPreparationFailure extends RuntimeException {

    public MailPreparationFailure(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Create `mail/MailSubmissionFailure.java`:

```java
package com.example.maildemo.mail;

public class MailSubmissionFailure extends RuntimeException {

    public MailSubmissionFailure(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Meaning:

- `MailPreparationFailure`: failed to construct a valid `MimeMessage`, such as address, encoding, or MIME issues.
- `MailSubmissionFailure`: Spring Mail reported an error during SMTP submission; deeper transport failure classification is needed before feeding a production retry pipeline.

Never treat every `MailSubmissionFailure` as definitely **not sent**. A timeout after SMTP `DATA` can be an `AMBIGUOUS` outcome because the relay may have accepted the message before the response was lost.

This example keeps error handling concise to stay focused on HTML/plain; production retries belong in an outbox with a failure classifier.

## 17. Sending Both HTML and Plain Text with MimeMessageHelper

This is the **most important part of the practice project**.

Create `mail/OrderMailService.java`:

```java
package com.example.maildemo.mail;

import java.io.UnsupportedEncodingException;
import java.util.UUID;

import com.example.maildemo.config.DemoMailProperties;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender sender;
    private final OrderMailRenderer renderer;
    private final DemoMailProperties properties;

    public OrderMailService(
            JavaMailSender sender,
            OrderMailRenderer renderer,
            DemoMailProperties properties) {
        this.sender = sender;
        this.renderer = renderer;
        this.properties = properties;
    }

    public SubmissionReceipt submitOrderConfirmation(
            OrderMailRequest request) {

        UUID notificationId = UUID.randomUUID();

        RenderedMail content = renderer.render(request);

        try {
            MimeMessage mime = sender.createMimeMessage();

            MimeMessageHelper helper = new MimeMessageHelper(
                mime,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
            );

            helper.setFrom(
                properties.from(),
                properties.fromName()
            );
            helper.setTo(request.to());
            helper.setReplyTo(properties.replyTo());
            helper.setSubject(content.subject());

            // Key point:
            // One email containing two display representations.
            helper.setText(
                content.plainText(),
                content.htmlText()
            );

            sender.send(mime);

            return new SubmissionReceipt(
                notificationId, "SUBMITTED"
            );

        } catch (MessagingException
                 | UnsupportedEncodingException exception) {

            throw new MailPreparationFailure(
                "Cannot prepare order-confirmation email",
                exception
            );

        } catch (MailException exception) {

            throw new MailSubmissionFailure(
                "SMTP submission reported an error",
                exception
            );
        }
    }
}
```

**Line to remember:**

```java
helper.setText(content.plainText(), content.htmlText());
```

This is the overload taking **two `String` arguments**:

- First parameter: **plain-text alternative**.
- Second parameter: **HTML alternative**.

It differs from:

```java
helper.setText(content.htmlText(), true);
```

The second overload only specifies an HTML body; it **does not** automatically generate a full plain-text version. To provide both, use the two-string overload.

### Why Choose an Explicit Multipart Mode?

```java
new MimeMessageHelper(
    mime,
    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
    "UTF-8"
)
```

`setText(plainText, htmlText)` requires the helper to be created in **multipart mode**. `MULTIPART_MODE_MIXED_RELATED` works well when the project may later add attachments or inline resources. Spring creates the `multipart/alternative` structure inside. Even in a demo without attachments, the helper may create outer multipart wrappers; that is valid.

If you use:

```java
new MimeMessageHelper(mime, false, "UTF-8")
```

and then call `setText(plain, html)`, the helper is not in multipart mode and cannot satisfy this case. Initialize the helper with `true` or an appropriate multipart mode.

## 18. Reviewing Each Call in the Service

| Call | Effect |
| --- | --- |
| `sender.createMimeMessage()` | Creates a Jakarta `MimeMessage` compatible with `JavaMailSender` |
| `new MimeMessageHelper(..., MIXED_RELATED, "UTF-8")` | Initializes multipart MIME helper and charset |
| `helper.setFrom(from, fromName)` | Sets `From` with a display name |
| `helper.setTo(to)` | Sets `To` recipient |
| `helper.setReplyTo(replyTo)` | Sets address receiving replies |
| `helper.setSubject(subject)` | Sets subject with encoding support |
| `helper.setText(plain, html)` | Creates two representations of the same content |
| `sender.send(mime)` | Submits message via SMTP configuration |
| `SubmissionReceipt(..., "SUBMITTED")` | Marks demo-level submission outcome |

In this example, `From` and `Reply-To` come from **application-controlled configuration**, not from the request body. This is a necessary guard against turning the endpoint into a sender-spoofing tool.

In production, verify that the sender domain/alias is authorized on the provider account. Successful SMTP AUTH does not automatically mean the provider allows any arbitrary `From` address.

## 19. MimeMessageHelper Does Not Replace JavaMailSender

Distinguish the roles:

```text
RenderedMail (data)
      |
      v
MimeMessageHelper (builder/helper)
      |
      v
MimeMessage (email MIME representation)
      |
      v
JavaMailSender (transport abstraction)
      |
      v
SMTP server
```

`MimeMessageHelper` neither opens connections nor sends emails. It operates on the constructed `MimeMessage`.

`JavaMailSender` neither renders Thymeleaf templates nor understands business DTOs. It receives a `MimeMessage` and submits it.

`MimeMessage` is the **email format**; `org.springframework.messaging.Message<?>` in Spring Integration is an internal message used in integration flows. Do not confuse the two concepts.

## 20. Creating a Demo API Active Only in the Local Profile

Create `mail/MailDemoController.java`:

```java
package com.example.maildemo.mail;

import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import jakarta.validation.Valid;

@RestController
@Profile("local")
@RequestMapping("/api/dev/order-confirmations")
public class MailDemoController {

    private final OrderMailService service;

    public MailDemoController(OrderMailService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<SubmissionReceipt> send(
            @Valid @RequestBody OrderMailRequest request) {

        return ResponseEntity.ok(
            service.submitOrderConfirmation(request)
        );
    }
}
```

`@Profile("local")` registers this endpoint bean only when the `local` profile is active. If `local` is accidentally enabled in production or the local port is exposed publicly without controls, it can still be abused. Thus **profiles are a demo guardrail, not a complete authentication/authorization mechanism**.

Production should trigger emails from authenticated use cases, order events, or an outbox, resolving recipients server-side with rate and abuse controls.

### Validation Errors

`@Valid @RequestBody` combined with Bean Validation checks `to`, `customerName`, and `orderCode`. On violation, Spring MVC returns a 4xx error per exception-handling configuration.

Remember that address format validation **does not verify that a mailbox exists** and does not prove the caller has permission to send order data to that address.

## 21. Demo Error Handling Without Returning Raw SMTP Exceptions

Create `mail/MailDemoErrorHandler.java`:

```java
package com.example.maildemo.mail;

import java.util.Map;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Profile("local")
public class MailDemoErrorHandler {

    @ExceptionHandler(MailPreparationFailure.class)
    public ResponseEntity<Map<String, String>> preparationError() {
        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(Map.of(
                "error", "MAIL_PREPARATION_FAILED"
            ));
    }

    @ExceptionHandler(MailSubmissionFailure.class)
    public ResponseEntity<Map<String, String>> submissionError() {
        return ResponseEntity
            .status(HttpStatus.BAD_GATEWAY)
            .body(Map.of(
                "error", "SMTP_SUBMISSION_FAILED_OR_UNCERTAIN"
            ));
    }
}
```

`SMTP_SUBMISSION_FAILED_OR_UNCERTAIN` intentionally does not claim "definitely not sent". If a client receives HTTP 502, **it must not automatically retry HTTP infinitely** without idempotency or notification lookup; an SMTP timeout after `DATA` can still mean the message was accepted.

This is a demonstration controller. In production, use a command/outbox ID, error classifier, retry policy, and persisted status.

## 22. Running the Project for the First Time

Start the SMTP catcher:

```bash
docker compose up -d
```

Then run Spring Boot with the local profile:

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=local
```

In some shells, passing Maven system properties requires quoting; in Windows PowerShell, you can set the profile via an environment variable:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
mvn spring-boot:run
```

Or with the built JAR:

```bash
java -jar target/mail-html-plain-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=local
```

If the JVM/app runs inside Docker, `localhost:1025` refers to its own container rather than the Mailpit container; use hostname `mailpit` on a shared Compose network or appropriate port mapping.

### Verifying the Services

- Spring Boot: `http://localhost:8080`.
- Mailpit web UI: `http://localhost:8025`.
- SMTP: `localhost:1025`.
- No SMTP username/password is required in this local environment.

If a port is already in use by another application, change the port binding and update `spring.mail.port` to match.

## 23. Sending the First Request

A `curl` command:

```bash
curl -X POST "http://localhost:8080/api/dev/order-confirmations" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "buyer@example.test",
    "customerName": "Nguyễn An",
    "orderCode": "ORD-2026-001"
  }'
```

A PowerShell command:

```powershell
$body = @{
    to = "buyer@example.test"
    customerName = "Nguyễn An"
    orderCode = "ORD-2026-001"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8080/api/dev/order-confirmations" `
    -ContentType "application/json; charset=utf-8" `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

When the SMTP catcher receives it successfully, an example response is:

```json
{
  "notificationId": "c751fb74-127d-4c5a-9b8a-38b1c7af3e4d",
  "submissionStatus": "SUBMITTED"
}
```

The UUID is generated fresh on each call; the sample above is illustrative. Sending the same request twice in this demo creates two submissions because **there is no idempotency/outbox yet**. Recognize this behavior before adding production safeguards.

## 24. Opening Mailpit to Inspect the Result

Visit `http://localhost:8025`, select the received email, and inspect:

- From: `Demo Workspace <no-reply@example.test>`.
- To: `buyer@example.test`.
- Reply-To: `support@example.test`.
- Subject: `Xác nhận đơn hàng ORD-2026-001`.
- HTML body with heading, recipient name, and button/link.
- Plain-text body with greeting, order code, and URL.
- MIME source showing parts with distinct `Content-Type` headers.

If the UI defaults to showing HTML, switch to the Text/Source tabs to confirm plain text was sent as well. Never assume MIME includes `text/plain` just because the HTML looks good; inspect both.

## 25. The MIME Structure Generated by the Helper

Conceptually:

```text
MimeMessage
    |
    v
multipart/alternative
    |
    +--> text/plain; charset=UTF-8
    |
    +--> text/html; charset=UTF-8
```

With `MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED`, the actual MIME tree may be wrapped like this:

```text
MimeMessage
  Content-Type: multipart/mixed
      |
      +--> multipart/related
              |
              +--> multipart/alternative
                      |
                      +--> text/plain; charset=UTF-8
                      |
                      +--> text/html; charset=UTF-8
```

When attachments or inline images are added, the tree gains corresponding parts. MIME headers and boundaries depend on the Jakarta Mail implementation and multipart mode; **never hardcode an assumption that top-level `Content-Type` is always `multipart/alternative`**.

Key idea: `multipart/alternative` represents **multiple ways to display the same information**. Clients can prefer either the HTML or plain-text version.

## 26. Plain Text Is Not "HTML with Tags Stripped"

An anti-pattern:

```java
String plain = html.replaceAll("<[^>]*>", "");
```

This regex is not an HTML parser. It can:

- Run sentences together when stripping `<p>`, `<br>`, `<li>`.
- Leave behind HTML entities such as `&amp;`.
- Lose the actual link URL inside `href`.
- Mishandle tables and hidden elements.
- Produce unreadable output in text-only clients.
- Alter the meaning of the email.

Plain text should be **authored separately from the same data**, including a greeting, key details, full links, and support instructions.

If an application has many templates, you can maintain a `.txt` template alongside `.html`, or use a dedicated plain-text renderer. Never rely on naive tag stripping.

## 27. Both Versions Must Be Semantically Equivalent

Compare the content:

| Information | Plain Text | HTML |
| --- | --- | --- |
| Greeting | Yes | Yes |
| Order code | Yes | Yes |
| Order status | Yes | Yes |
| View-order URL | Written out in full | Placed in `<a>` |
| Support instructions | Yes | Yes |
| Branding | Yes, as text | Yes, with styling |
| Sensitive data | Only what is necessary | Same minimal level |

Never put cancellation terms or mandatory links in HTML without including them in plain text. An email may be rendered purely in plain text on clients using security mode or accessibility tools.

### Handling Long Plain-Text Details

For multi-field summaries, you can format like this:

```text
Order details
-------------
Order code : ORD-2026-001
Status     : Recorded
View details:
http://localhost:8080/orders/ORD-2026-001
```

Avoid wide monospace tables that force mobile readers to scroll horizontally.

## 28. Where Does UTF-8 Matter?

An email containing:

```text
Tên: Nguyễn An
Subject: Xác nhận đơn hàng – Tháng 11
Body: Đơn hàng của bạn đã được ghi nhận.
```

Places that must handle encoding:

1. **Java source/resource files** saved as UTF-8.
2. **Thymeleaf template** read with the right encoding.
3. **`MimeMessageHelper` charset UTF-8**.
4. **Subject/From display name** encoded properly by Jakarta Mail at the MIME layer.
5. **HTTP request JSON** sent as UTF-8 when calling the API.
6. **SMTP test viewer** decoding MIME parts per charset.

In the example:

```java
new MimeMessageHelper(
    mime,
    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
    "UTF-8"
);
```

and:

```java
helper.setFrom(
    "no-reply@example.test",
    "Đội hỗ trợ"
);
```

`MimeMessageHelper` works with Jakarta Mail to encode display names and headers properly. Raw MIME headers may appear as encoded-words rather than literal Unicode characters.

In tests, call `mime.getSubject()` to inspect the decoded value. Never compare the subject directly against raw MIME header bytes.

## 29. Content-Type and HTML Are Not Just a Boolean at the Transport Layer

Two important overloads:

```java
helper.setText("Xin chào");          // plain text
helper.setText("<b>Xin chào</b>", true); // HTML only
```

And:

```java
helper.setText(
    "Xin chào, đơn hàng đã xác nhận.",
    "<html><body><b>Xin chào</b></body></html>"
); // plain + HTML alternatives
```

The boolean `true` in the `(String, boolean)` two-argument overload means **the first string is HTML**; it does not mean a plain-text alternative is automatically created.

The `(String, String)` overload is for **plain + HTML**. Watch the parameter order: plain first, HTML second.

Real-world bugs happen from calling:

```java
helper.setText(html, plain);
```

Reversing the order assigns mismatched `Content-Type` headers to the parts, causing HTML to render as raw source or plain text to appear inside the HTML part.

## 30. Do Not Call setText Twice to Create Alternatives

Avoid:

```java
helper.setText(plain);
helper.setText(html, true);
```

This is not the contract for creating two alternatives. The second call may overwrite the first part or produce unintended results depending on the implementation and multipart mode.

Call it **once**:

```java
helper.setText(plain, html);
```

If you need a highly custom MIME structure, construct the multipart tree explicitly using the Jakarta Mail API. For standard transactional emails, this overload keeps the code simpler and less error-prone.

## 31. From vs. Reply-To

In the example:

```java
helper.setFrom("no-reply@example.test", "Demo Workspace");
helper.setReplyTo("support@example.test");
```

Illustrative headers:

```text
From: Demo Workspace <no-reply@example.test>
Reply-To: support@example.test
```

`From` represents the sender visible to the recipient. `Reply-To` indicates where replies should go if the customer hits Reply, which may differ from `From`.

Do not confuse these with:

- SMTP AUTH username: the account authenticating the submission.
- SMTP envelope `MAIL FROM`: the transport-level bounce/return-path address.
- Provider verified sender/domain: the identity authorized to send.
- `Sender` header: has distinct semantics in MIME.

A provider may require `From` to belong to a verified domain or have send-as permission. `setFrom` succeeding during MIME construction does not guarantee the relay will accept an arbitrary sender.

## 32. To, Cc, Bcc, and Recipient Privacy

The practice project uses a single `To`. With multiple recipients:

```java
helper.setTo(new String[] {
    "buyer1@example.test",
    "buyer2@example.test"
});
helper.setCc("audit@example.test");
helper.setBcc("internal@example.test");
```

Keep in mind:

- `To`/`Cc` are generally visible to all recipients.
- `Bcc` must not be exposed in delivered MIME headers; the SMTP envelope handles delivery to those addresses.
- Sending one message to many recipients makes personalization and per-recipient tracking awkward.
- Marketing mail requires per-recipient consent, unsubscribe links, and frequency caps.
- Never log `getAllRecipients()`/Bcc arrays or copy `Bcc` into custom public headers.

In production, users must not be allowed to supply unbounded recipient lists through a public API.

## 33. MIME Alternatives Are One Content Item, Not Two Emails

A concept to keep clear:

```text
One logical email
    |
    +--> Alternative #1: text/plain
    |
    +--> Alternative #2: text/html
```

Never call:

```java
sender.send(plainMimeMessage);
sender.send(htmlMimeMessage);
```

just to provide a fallback. Doing so sends **two separate emails** instead of creating a MIME alternative.

The right approach is building **one `MimeMessage`** and adding **two body parts** via `MimeMessageHelper#setText(plain, html)`.

For tracking and deduplication, one notification ID corresponds to one logical email; the plain and HTML parts do not get separate notification IDs.

## 34. Unit Testing with Mockito Without Sending via SMTP

Service test goals:

1. The plain-text version is generated.
2. The HTML version contains the expected content.
3. `JavaMailSender.send(...)` receives **one `MimeMessage`**.
4. The `MimeMessage` has the expected Subject, `To`, and `From`.
5. The MIME tree contains both `text/plain` and `text/html`.
6. Unit tests do not require a real connection to Mailpit.

Here we use Mockito and an in-memory Jakarta Mail `Session`. Spring Boot starter test supplies Mockito and JUnit matching dependency management.

### Test setup

```java
package com.example.maildemo.mail;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.util.Properties;

import com.example.maildemo.config.DemoMailProperties;
import jakarta.mail.Address;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

import org.thymeleaf.TemplateEngine;
import org.thymeleaf.TemplateMode;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

class OrderMailServiceTest {

    private JavaMailSender sender;
    private OrderMailService service;

    @BeforeEach
    void setUp() {
        sender = mock(JavaMailSender.class);

        when(sender.createMimeMessage()).thenAnswer(invocation ->
            new MimeMessage(Session.getInstance(new Properties()))
        );

        ClassLoaderTemplateResolver resolver =
            new ClassLoaderTemplateResolver();

        resolver.setPrefix("templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);

        DemoMailProperties properties = new DemoMailProperties(
            "no-reply@example.test",
            "Demo Workspace",
            "support@example.test",
            "http://localhost:8080"
        );

        OrderMailRenderer renderer =
            new OrderMailRenderer(engine, properties);

        service = new OrderMailService(
            sender, renderer, properties
        );
    }

    @Test
    void sendsPlainAndHtmlAlternatives() throws Exception {
        OrderMailRequest request = new OrderMailRequest(
            "buyer@example.test",
            "Nguyễn An",
            "ORD-2026-001"
        );

        SubmissionReceipt receipt =
            service.submitOrderConfirmation(request);

        assertEquals("SUBMITTED", receipt.submissionStatus());
        assertNotNull(receipt.notificationId());

        ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender, times(1)).send(captor.capture());

        MimeMessage actual = captor.getValue();
        actual.saveChanges();

        assertEquals(
            "Xác nhận đơn hàng ORD-2026-001",
            actual.getSubject()
        );

        Address[] recipients =
            actual.getRecipients(Message.RecipientType.TO);

        assertEquals(1, recipients.length);
        assertEquals(
            "buyer@example.test",
            ((InternetAddress) recipients[0]).getAddress()
        );

        String plain = MimeParts.findText(
            actual, "text/plain"
        );
        String html = MimeParts.findText(
            actual, "text/html"
        );

        assertNotNull(plain);
        assertNotNull(html);
        assertTrue(plain.contains("ORD-2026-001"));
        assertTrue(plain.contains("Nguyễn An"));
        assertTrue(plain.contains(
            "http://localhost:8080/orders/ORD-2026-001"
        ));

        assertTrue(html.contains("Xác nhận đơn hàng"));
        assertTrue(html.contains("Nguyễn An"));
        assertTrue(html.contains("ORD-2026-001"));
    }
}
```

`org.thymeleaf.spring6.SpringTemplateEngine` matches Thymeleaf's Spring Framework 6 integration in this Boot 3.x example. When upgrading to another framework generation, imports may change per dependency version.

In unit tests, `verify(sender).send(...)` proves **the service invoked `JavaMailSender` once**, not that a real SMTP relay received the email. Transport testing requires an SMTP catcher or dedicated test server.

## 35. Helper to Traverse the MIME Tree in Tests

With nested multipart modes, never cast directly:

```java
String body = (String) mime.getContent();
```

Top-level `getContent()` may return a `Multipart`, not a `String`.

Create test helper `MimeParts`:

```java
package com.example.maildemo.mail;

import jakarta.mail.Multipart;
import jakarta.mail.Part;

final class MimeParts {

    private MimeParts() {}

    static String findText(
            Part part, String wantedType) throws Exception {

        if (Part.ATTACHMENT.equalsIgnoreCase(
                part.getDisposition())) {
            return null;
        }

        if (part.isMimeType(wantedType)) {
            Object content = part.getContent();

            if (content instanceof String text) {
                return text;
            }
        }

        if (part.isMimeType("multipart/*")) {
            Multipart multipart =
                (Multipart) part.getContent();

            for (int i = 0; i < multipart.getCount(); i++) {
                String found = findText(
                    multipart.getBodyPart(i),
                    wantedType
                );

                if (found != null) {
                    return found;
                }
            }
        }

        return null;
    }
}
```

Why recursive traversal is required: HTML and plain text typically reside inside `multipart/alternative` nested under `multipart/related` or `multipart/mixed`.

This is a test helper for demo emails, not a hardened MIME parser for arbitrary Internet emails. Production parsers must limit nesting depth, part counts, and total decoded bytes, and safely handle nested `message/rfc822` or malformed MIME.

## 36. Testing HTML Escaping with Synthetic Data

An additional test:

```java
@Test
void escapesUntrustedCustomerNameInHtml() {
    OrderMailRequest request = new OrderMailRequest(
        "buyer@example.test",
        "<img src=x onerror=alert(1)>",
        "ORD-2026-002"
    );

    RenderedMail rendered =
        renderer.render(request);

    assertFalse(rendered.htmlText().contains(
        "<img src=x onerror=alert(1)>"
    ));
    assertTrue(rendered.htmlText().contains(
        "&lt;img"
    ));
}
```

This test expects `renderer` to be initialized as a field on the test class rather than a local variable in `setUp`; the snippet illustrates how to assert HTML escaping at the renderer level. You can split it into `OrderMailRendererTest` using the same Thymeleaf resolver setup to keep tests focused.

Thymeleaf `th:text` escapes HTML metacharacters in text contexts. **Do not rely on a regex validator on `customerName` to prevent HTML injection**; HTML escaping must occur in the output context.

A JavaScript string represented as text in HTML may still appear in escaped form; what matters is checking that it never becomes executable markup.

## 37. Cross-Checking Plain and HTML Content in Tests

In practice, build an assertion table covering both bodies:

| Content | Plain Text | HTML |
| --- | --- | --- |
| Customer name | Present | Present, escaped |
| Order code | Present | Present |
| Absolute URL | Present | Present in `href` |
| Support guidance | Present | Present |
| Subject | No need to repeat in body | May appear as heading |
| HTML tags | No forced markup | Has markup |
| Text-only readability | Yes | Not applicable |

Never test HTML by matching a full verbatim string with exact whitespace and CSS attribute ordering. Template engines can alter formatting. Test **semantic content**, escaped values, and MIME parts.

For URLs, verify they belong to an allowed domain and contain no unintended redirect or tracking tokens.

## 38. End-to-End Testing with an SMTP Catcher

In addition to Mockito, run the real app with Mailpit and send a request:

```text
HTTP request
      |
      v
Spring Controller
      |
      v
Renderer + MimeMessageHelper
      |
      v
JavaMailSenderImpl
      |
      v
TCP localhost:1025
      |
      v
Mailpit SMTP
      |
      v
Captured MIME + UI
```

Items to verify in Mailpit:

1. Exactly **one** message arrives per API call.
2. Subject displays Vietnamese characters without encoding corruption.
3. `From` display name preserves diacritics if customized in config.
4. `To` and `Reply-To` are accurate.
5. HTML renders the link button and escapes the customer name.
6. Plain text has real readable text, not `<p>...</p>`.
7. MIME source contains both `text/plain` and `text/html`.
8. Each part's `Content-Type` specifies the proper charset.
9. When Mailpit stops running, the API reports a submission error.
10. SMTP is not automatically called a second time when the client sends one request.

Mailpit capture tests **submission and MIME content**, not Gmail/Outlook inbox placement or email reputation.

## 39. Stopping Mailpit to Test Connection Errors

In the local environment:

```bash
docker compose stop mailpit
```

Call the API again. When Spring Mail cannot connect to `localhost:1025`, it raises `MailSendException` or a `MailException` subtype. The controller advice returns a safe error response.

Then start it again:

```bash
docker compose start mailpit
```

Key lessons:

- Explicit connection failures before sending a message can be retried per policy.
- The current demo **has no queue and performs no automatic retries**.
- Client-side HTTP retries can create duplicate emails if the prior response outcome was unclear.
- When adding a production outbox, preserve a stable notification ID, idempotency, and error classification.

Never start by adding `@Retryable(retryFor=MailException.class)` to every exception and claiming emails will never be lost or duplicated.

## 40. Why Is the Plain-Text Alternative Still Important When HTML Looks Great?

Benefits:

- Supports email clients that do not render HTML.
- Supports distraction-free plain-text reading.
- Improves core content accessibility across environments.
- Suits users who choose text-only mode.
- Helps automated mail processors locate plain-text information.
- May be handled differently during provider/client filtering.

However, plain text **does not guarantee deliverability on its own**. Delivery quality also depends on domain authentication, sender reputation, consent, bounce rates, IP reputation, content, providers, and recipient policies.

Never add a plain-text part containing just an empty string. Ensure recipients can actually understand the message.

## 41. Creating Long Plain Text with a Dedicated Template

When emails grow long, hardcoded `String.formatted` blocks become hard to maintain. You can use a separate text template file:

```text
Xin chào [[${customerName}]],

Đơn hàng [[${orderCode}]] của bạn đã được ghi nhận.

Xem đơn hàng: [[${orderUrl}]]

Trân trọng,
Demo Workspace
```

This is Thymeleaf's inline expression syntax **for the `TEXT` template mode**, not an arbitrary `.txt` file that Spring Boot's Thymeleaf HTML resolver will automatically process properly.

If implemented:

- Configure a `TemplateMode.TEXT` resolver with its own prefix/suffix.
- Ensure it does not conflict with the HTML resolver.
- Share the same `Context`/render model across both.
- Control line breaks and whitespace carefully.
- Test that no unwanted HTML entities or escaping appear in plain text.

For a small demo, keeping plain text in Java reduces configuration. As template counts grow, dedicated text and HTML template systems are cleaner.

## 42. Never Use th:utext on User Input

In Thymeleaf:

```html
<span th:text="${customerName}">Tên</span>
```

is the standard choice for dynamic text.

Conversely:

```html
<span th:utext="${customerName}">Tên</span>
```

can inject **unescaped HTML** into the email. If `customerName` contains markup, that markup can become active HTML rather than plain text.

Email clients may sanitize portions of HTML, yet **never rely on the client to make content safe**. For author-controlled rich content, build a dedicated sanitization pipeline and trust boundary.

This lesson uses only `th:text` and validated fields.

## 43. Email URLs Must Be Server-Controlled

Example:

```java
String orderUrl =
    properties.publicBaseUrl()
        + "/orders/" + request.orderCode();
```

is sound only when:

- `publicBaseUrl` belongs to a trusted domain from config.
- `orderCode` is restricted to safe characters.
- The `/orders/{id}` endpoint enforces authentication and authorization.
- The URL contains no bearer tokens or long-lived secrets.
- The `Host` header from HTTP requests is never used to construct email links.

In real applications, prefer a URL builder that properly encodes path segments alongside an HTTPS allowlist. Whenever an order code permits characters outside `[A-Z0-9-]`, encode it properly instead of concatenating blindly.

An email containing a valid link does not make the underlying resource public; the web app still needs resource authorization.

## 44. Do We Need to Send a Logo Image?

Not required. Your first project should focus on getting the two alternatives right.

If an inline logo is needed later:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setText(plainText, htmlText);

// HTML contains: <img src="cid:companyLogo">
helper.addInline(
    "companyLogo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
```

With inline CIDs, the HTML and Content-ID must match. Per standard helper usage, call `setText(...)` before adding inline resources.

Inside a JAR, `ClassPathResource` does not necessarily map to a real filesystem path; avoid calling `getFile()` and assuming it always succeeds. Use resource or input-stream APIs supported by Spring.

An inline image is a separate MIME part; **it does not replace `text/plain`**. Never log raw image bytes when debugging emails.

## 45. What About Adding a PDF Attachment?

An extension:

```java
helper.setText(plainText, htmlText);

helper.addAttachment(
    "invoice.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
```

Required import:

```java
import org.springframework.core.io.ByteArrayResource;
```

Illustrative order: build the plain/HTML alternatives first, then add attachments to the MIME message.

Production notes:

- Cap PDF sizes and total MIME message size.
- `ByteArrayResource` keeps all bytes in memory; suitable only for small files.
- For larger files, use a resource or `InputStreamSource` backed by a **repeatable** stream.
- Never put internal paths or unnecessary PII in attachment filenames.
- Verify access permissions to the document before sending.
- Message size after MIME/base64 encoding will exceed the raw file size.
- The MIME structure must still preserve both plain and HTML alternatives.

Never place attachment bytes in JSON requests or system logs.

## 46. MIME Parts and Client Display Preferences

Many email clients choose how to display a message from its alternative parts. Conceptually, the standard layout is:

```text
multipart/alternative
  1. text/plain
  2. text/html
```

Some clients render HTML because they support rich content; others may render text. **This does not mean the email was sent twice.**

Tests should not depend directly on raw MIME boundary string ordering because the helper may wrap parts inside `mixed`/`related`. Parse the MIME tree, locate content types, and inspect decoded content instead.

When building an email with both HTML/plain and attachments, initialize the helper with a multipart mode supporting complex layouts; never manually force top-level `Content-Type` to `text/html` after the helper has created a multipart message.

## 47. Should You Set the Content-Type Header Manually?

There is no need for:

```java
mime.setHeader("Content-Type", "text/html; charset=UTF-8");
```

after calling `MimeMessageHelper#setText(plain, html)`. Overwriting the top-level `Content-Type` can break the multipart structure because the actual content consists of multiple parts rather than a single HTML string.

Let the helper and Jakarta Mail generate the proper MIME headers, encodings, and boundaries. To customize the charset, pass it to the helper constructor; for HTML-only emails, use the appropriate overload while understanding the trade-offs.

`MIME-Version`, `Content-Transfer-Encoding`, and multipart boundaries are transport-level details; never assemble them manually via string concatenation in a service.

## 48. Differences Between SimpleMailMessage and MimeMessage

| Capability | `SimpleMailMessage` | `MimeMessage` + helper |
| --- | --- | --- |
| Simple plain text | Yes | Yes |
| Standalone HTML | Not its main purpose | Yes |
| Plain + HTML alternative | No | Yes |
| Multipart attachments | No | Yes |
| Inline CID images | No | Yes |
| Unicode subject | Yes via mail sender | Yes, explicitly MIME-configured |
| Rich MIME headers | Limited | Yes |
| Inspectable MIME tree in tests | Not as a MIME object | Yes |

`SimpleMailMessage` suits simple plain-text notifications. When the requirement is **both HTML and plain text in one email**, use `JavaMailSender` with `MimeMessageHelper`.

## 49. Common Errors and Fixes Table

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| HTML renders as literal `<p>` | Sent as `text/plain` | Use `setText(plain, html)` |
| Email contains HTML only | Used `setText(html, true)` | Add plain text with the two-String overload |
| Helper complains not in multipart mode | Initialized helper with `false` | Use an appropriate multipart mode |
| Corrupted Vietnamese Subject | Source/helper/resource encoding | Use UTF-8 end-to-end |
| Template not found | Wrong path or resolver suffix | `templates/mail/order-confirmation.html` |
| Name with `<script>` alters markup | Used unescaped HTML | Use `th:text`/escaping |
| Link points to unfamiliar domain | Unchecked base URL from request | Server-side allowlisted base |
| SMTP connection refused | Mailpit not running or wrong host/port | Check `localhost:1025` and container networking |
| Production SMTP AUTH error | Wrong credentials or mechanism | Check provider secrets and config |
| STARTTLS/certificate failure | Wrong TLS/hostname/cert | Check provider TLS requirements |
| Mailpit receives no email | Wrong profile or port config | Check safe app logs and SMTP host |
| Two emails sent | API called twice or code sends two messages | Check requests and idempotency |
| MIME source has `multipart/mixed` | Helper mode adds wrapper | Traverse nested alternative parts |
| Empty attachment | Stream is not repeatable | Use a repeatable `InputStreamSource` |
| Test fails casting `Multipart` to `String` | Top-level multipart | Traverse MIME recursively |
| HTTP 502 even though email arrived | Timeout after `DATA` | Classify as `AMBIGUOUS`; avoid blind retries |

This table helps trace issues from **content preparation** to **SMTP submission** rather than treating every failure as identical.

## 50. SMTP Accepted Does Not Mean Delivered

A demo response:

```json
{
  "notificationId": "opaque-uuid",
  "submissionStatus": "SUBMITTED"
}
```

means the application invoked the sender without throwing an exception. It does not prove:

- The target mailbox exists.
- The email landed in the Inbox rather than Spam.
- The recipient opened or read it.
- Links were clicked.
- The provider won't emit a bounce later.

With local Mailpit, it means the SMTP catcher accepted the message for inspection. In production, the application needs provider delivery/bounce events to track downstream status.

An HTTP request timing out is **not enough** to conclude the relay never accepted the message. That is why idempotent commands or a durable outbox are needed when adding a real API.

## 51. Why Does the Demo Send Synchronously While Production Usually Needs an Outbox?

Demo:

```text
HTTP request
    |
    v
Build MimeMessage
    |
    v
JavaMailSender.send()
    |
    v
HTTP response
```

Simple and ideal for learning `MimeMessageHelper`. In transactional systems, however:

- Slow SMTP can time out HTTP requests.
- If the business transaction commits and SMTP then fails, email intent can be lost.
- Client HTTP retries easily create duplicates.
- Process restarts lose in-memory work.
- There is no durable attempt history.
- There is no rate limiting, retry policy, or bounce tracking.

A production architecture:

```text
Business transaction
  +--> Order state update
  +--> Mail outbox intent
  |
  v
COMMIT
  |
  v
Background worker
  |
  +--> Load content or immutable snapshot
  +--> Render HTML + plain
  +--> Build MimeMessageHelper
  +--> SMTP submit
  +--> Persist outcome
  |
  v
Provider delivery events / reconciliation
```

The **HTML/plain rendering and MIME construction** remain completely reusable; only how sending is triggered and state is persisted changes.

Never hold a database transaction open across `JavaMailSender.send(...)`, because SMTP side effects cannot roll back with a DB transaction.

## 52. Choosing When to Render Across Retries

There are two strategies:

**Render once, store a snapshot / immutable content:**

- Retry attempts for the same notification preserve the exact subject/body/version.
- Suitable for invoices or auditable emails.
- Requires protecting stored HTML/text and artifact references.
- Requires encryption, ACLs, and proper retention policies.

**Re-render on each attempt:**

- Can pick up fresher data.
- Content may shift between attempts of a single notification.
- Template deployments may cause HTML and plain versions to diverge if versions shift.
- Links or OTPs may expire.

For transactional emails, explicitly decide content versioning and the source of truth. Never assume an application retry is always allowed to reuse an old security token.

## 53. Reusing MailService Without Creating Duplicates

An outbox worker might have a method:

```java
public void process(MailJob job) {
    if (!eligibility.canSend(job)) {
        states.markSuppressed(job);
        return;
    }

    PreparedMail prepared = renderer.prepare(job);

    try {
        mailSubmissionPort.submit(prepared);
        states.markSubmitted(job);
    } catch (TransientMailFailure exception) {
        states.scheduleRetry(job);
    } catch (AmbiguousMailFailure exception) {
        states.markAmbiguous(job);
    }
}
```

This is domain pseudocode, not a built-in Spring Mail API. It highlights:

- Retries belong in orchestration/outbox.
- MIME rendering belongs in renderer/builder.
- SMTP sending belongs in the adapter.
- State updates require owner/lease/version guards.
- Never blindly retry when the SMTP outcome is ambiguous.

The direct demo lacks these components and should not be treated as a complete production delivery system.

## 54. Safe Logging When Sending HTML

Never do this:

```java
log.info("mail={}", mimeMessage);
log.debug("html={}", renderedMail.htmlText());
log.debug("plain={}", renderedMail.plainText());
```

Message bodies may contain names, order numbers, addresses, URL tokens, payment details, and attachments.

A concise event:

```java
log.info(
    "event=mail.smtp.submitted notificationId={} "
        + "category={} durationMs={}",
    notificationId,
    "ORDER_CONFIRMATION",
    elapsedMs
);
```

When a provider fails, log a normalized failure class or safe SMTP code; never print raw exceptions containing recipients or SMTP transcripts into general logs.

Never enable `mail.debug=true` or `Session.setDebug(true)` in production to inspect full MIME payloads, as protocol debug logs can expose wire exchanges, recipients, and payloads.

## 55. Securing the Mail-Sending Endpoint

Even though the demo API runs only under the `local` profile, real deployments require:

1. Caller authentication.
2. Authorization on the order/resource.
3. Server-side recipient resolution from the verified order/customer.
4. Rate limits per user, tenant, IP, and campaign.
5. Idempotency keys for send commands.
6. Suppression/consent policies per email type.
7. Provider-verified `From` address/domain.
8. Allowlisted template keys; never arbitrary HTML from clients.
9. Size limits on Subject, HTML, and attachments.
10. CSRF/CORS settings matching the auth model.
11. Auditing who requested the send and why.
12. Business expiry and quiet hours where applicable.
13. SMTP credentials in a secret manager.
14. Production TLS and hostname verification.
15. Never exposing Mailpit or capture UIs to the Internet.

A "test send" endpoint must never be deployed as an open relay simply because it uses `JavaMailSender` cleanly.

## 56. If Using Spring Integration Mail

In Spring Integration, `Message<?>` carries a payload and headers; it is not the same as Jakarta `MimeMessage`. To send rich emails:

```text
Business event
      |
      v
Spring Integration Message<MailIntent>
      |
      v
Transformer / service activator
      |
      v
RenderedMail + MimeMessageHelper
      |
      v
JavaMailSender.send(MimeMessage)
```

Or use Spring Integration Mail outbound mapping for simpler payloads. For the HTML/plain alternative emails in this lesson, a service activator or custom adapter building `MimeMessage` explicitly is easier to control.

Never assume setting a `contentType=text/html` header on Spring Integration `MessageHeaders` automatically builds a MIME alternative. Explicit mapping at the boundary is required.

## 57. Practice Project Handoff Checklist

- [ ] Maven includes Mail, Web, Validation, and Thymeleaf dependencies.
- [ ] JDK, Boot, and Jakarta Mail packages are compatible.
- [ ] Local Mailpit SMTP is running.
- [ ] Spring Boot runs with the `local` profile.
- [ ] SMTP host/port are right, with debug off by default.
- [ ] `DemoMailProperties` binds `from`, `fromName`, `replyTo`, and URL.
- [ ] Request DTO validates email, name, and `orderCode`.
- [ ] HTML template uses `th:text` for dynamic text.
- [ ] URLs use trusted base config, never the HTTP `Host` header.
- [ ] Dedicated plain-text version contains complete information.
- [ ] Renderer returns `RenderedMail(subject, plain, html)`.
- [ ] Service creates `MimeMessage` via `JavaMailSender`.
- [ ] Helper is initialized in multipart mode with `"UTF-8"`.
- [ ] `helper.setText(plainText, htmlText)` is called in the right order.
- [ ] Service calls `sender.send(mime)` **once**.
- [ ] Mailpit shows exactly one email with both alternatives.
- [ ] Vietnamese Subject and names render cleanly.
- [ ] Tests traverse the MIME tree instead of casting top-level content to `String`.
- [ ] HTML escaping is verified with synthetic payloads.
- [ ] When SMTP is unavailable, the API reports an error instead of claiming delivered.
- [ ] Raw MIME, recipients, OTPs, and attachments are never logged.
- [ ] Clear distinction between synchronous demo and production outbox/idempotency.

## 58. Guided Extension Exercises

**Exercise 1 — Customize Content**

Add `shippingDate` to the demo request model; include a corresponding sentence in both plain text and HTML, formatted for the Vietnamese locale. Assert that both alternatives convey the same meaning.

**Exercise 2 — Safe URLs**

Use a URI/path builder to encode the order path segment instead of string concatenation if `orderCode` allows special characters. Ensure the base URL is allowlisted and production enforces HTTPS.

**Exercise 3 — Inline Logo**

Place a test logo on the classpath, reference it via `cid:companyLogo` in HTML, invoke `addInline` after `setText`, and verify MIME contains the matching Content-ID. Keep the plain text meaningful without relying on images.

**Exercise 4 — PDF Attachment**

Attach a small PDF fixture using `ByteArrayResource`, verifying content type, filename, and bytes. Ensure attachments are never logged and size limits are enforced when scaling.

**Exercise 5 — Template Versioning**

Include `templateVersion` in the render model and record it in notification metadata. When retrying the same logical intent, deliberately decide whether to reuse the old snapshot or re-render.

**Exercise 6 — Content Quality Unit Tests**

Write tests verifying plain text contains the real link, HTML escapes untrusted data, and MIME has both alternative body types. Avoid asserting equality on full raw MIME bytes because boundaries and encoded headers may vary.

**Exercise 7 — Production Outbox**

Replace the synchronous API with a command persisting notification intent to a database, add a `@Scheduled` worker that claims and sends after commit with idempotency, leases, and retries. Never treat `@Async` alone as a durable queue.

## 59. Self-Check Questions

1. Why is sending two separate emails (one HTML, one text) not equivalent to a MIME alternative?
2. How does the `setText(String, boolean)` overload differ from `setText(String, String)`?
3. Why does `setText(plain, html)` require multipart mode?
4. Can an email with a top-level `multipart/mixed` contain a `multipart/alternative`?
5. Why should plain text not be generated by stripping HTML tags with regex?
6. Why must HTML from user input be escaped even if email clients apply sanitization?
7. When a `From` display name contains Vietnamese characters, where does charset encoding matter?
8. Does `JavaMailSender.send()` succeeding prove Inbox delivery?
9. If Mailpit receives no emails, which configuration points should you check first?
10. Why does the demo API use `@Profile("local")` while production still needs auth and authorization?
11. If an HTTP client retries after a timeout, what can cause duplicate emails?
12. How do you inspect HTML and plain text in a MIME tree without a `ClassCastException`?
13. When adding an attachment, how does the MIME structure change?
14. In production, how should responsibilities be divided among renderer, outbox worker, and SMTP adapter?
15. Should an OTP email be resent with its raw HTML once the token has expired?

These questions focus on understanding MIME fundamentals and production boundaries rather than memorizing a few config lines.

## 60. Summary

- `JavaMailSender` sends mail over SMTP; `MimeMessageHelper` helps construct MIME emails.
- Plain text and HTML are **not two emails**, but two alternative parts in one message.
- Use the **`helper.setText(plainText, htmlText)`** overload to provide both parts.
- Initialize the helper in **multipart mode** with `"UTF-8"` to support alternatives and Vietnamese text.
- Use `th:text` in Thymeleaf for dynamic values and avoid unescaped HTML concatenation.
- Author plain text explicitly with the full order code and URL.
- Top-level MIME may be `multipart/mixed` or `related`; look for the nested `multipart/alternative`.
- Mailpit is well-suited for local testing without reaching real mailboxes.
- Mockito tests verify the service and MIME; SMTP capture tests verify the transport boundary.
- `From` and `Reply-To` are mail headers, not SMTP credentials.
- Taking `To` from the request fits a restricted demo only; production must authorize the business resource and recipient.
- `send()` succeeding means submission at the current hop, not delivered or opened.
- Never blindly retry after a timeout because the SMTP relay may already have accepted the message.
- When scaling to production, keep the renderer/builder and move orchestration into a durable outbox with idempotency, quotas, and auditing.

**Outcome achieved:** the application builds a `MimeMessage` with a **cleanly formatted HTML version** and a **readable plain-text version** from the same order data via `MimeMessageHelper` and `JavaMailSender`. This implementation establishes a clean foundation for adding attachments, inline images, template versioning, retries/outbox, and provider tracking while preserving clear boundaries between email content and transport.
