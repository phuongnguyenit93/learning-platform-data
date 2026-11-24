# HTML templates and data inserted from the application

In **Spring Framework Mail**, an email can contain HTML content to present order notifications, registration confirmations, invoices, or service updates. Unlike a plain-text message, HTML content usually has layout, colors, link buttons, information tables, and images. However, writing a fixed HTML string in Java is not suitable when each recipient has a **different name, order number, amount, and link**.

A common solution is to separate the **HTML template** from the **business data**. The application collects and validates the data, a template engine produces the complete HTML, and then `JavaMailSender` sends that HTML inside a MIME message.

~~~text
Order / Account / Notification service
              |
              v
  Data for the email (DTO)
              |
              v
  Template engine + HTML template
              |
              v
     Rendered HTML string
              |
              v
   MimeMessage + MimeMessageHelper
              |
              v
    JavaMailSender -> SMTP provider
~~~

In this article, we use **Thymeleaf** as the template engine example in Spring Boot. This is not a mandatory choice: FreeMarker, Mustache, or another HTML-building tool can also be used if the application integrates it appropriately. The important part is to understand the boundary between the **template content**, the **data inserted into the template**, and the **mail-sending mechanism**.

## 1. Why separate HTML from Java?

A mail-sending method may start out by concatenating strings:

~~~java
String html = "<html><body>"
        + "<h1>Hello " + customerName + "</h1>"
        + "<p>Order " + orderId + " has been confirmed.</p>"
        + "</body></html>";
~~~

This approach seems quick but causes many problems:

- **Hard to maintain:** changing the HTML/CSS layout requires editing Java, and it is easy to miss quotes, closing tags, or escape characters.
- **Hard to reuse:** emails for multiple languages, brands, or transaction types often share common UI fragments.
- **Hard to test:** presentation is interleaved with business logic, making it difficult to preview an email.
- **Security risk:** user data concatenated directly into HTML may contain `<`, `>`, quotes, or disallowed markup.
- **Hard to provide a text version:** an HTML email should still have a plain-text alternative for email clients that do not display HTML.

Instead of building HTML by joining many strings, the application can use a template:

~~~html
<h1>Hello <span th:text="${customerName}">Customer</span></h1>
<p>
  Order
  <strong th:text="${orderId}">A123</strong>
  has been confirmed.
</p>
~~~

Here:

- **The HTML and layout** are defined by the template file.
- **`customerName` and `orderId`** are application data passed in at render time.
- **`th:text`** tells Thymeleaf to replace the element's text with the corresponding value, while also escaping special characters appropriately for the HTML context.
- **The default values** between the tags help the template author see where the data goes, and are replaced when the template is processed.

The template engine produces a complete HTML string; **it does not send email**. Sending is done separately by Spring Mail.

## 2. Three layers of responsibility to distinguish

| Layer | Question it answers | Example |
| --- | --- | --- |
| **Business data** | What content needs to be conveyed? | Customer, order, amount, status |
| **Presentation/template** | How is the information expressed in HTML? | The `order-confirmation.html` file, CSS, logo, tables |
| **Sending email** | How is the message delivered to the SMTP provider? | `JavaMailSender`, `MimeMessageHelper`, `spring.mail.*` configuration |

A reasonable boundary:

~~~mermaid
flowchart LR
    A["OrderService"] --> B["OrderMailData"]
    B --> C["Thymeleaf Renderer"]
    D["order-confirmation.html"] --> C
    C --> E["Rendered HTML"]
    B --> F["Plain-text Renderer"]
    E --> G["MimeMessageHelper"]
    F --> G
    G --> H["JavaMailSender"]
    H --> I["SMTP provider"]
~~~

**OrderService** does not need to know how many columns the HTML content is divided into. The **template engine** does not need to know the SMTP account, password, or retry policy. The **mail sender** should not query orders or adjust data according to business logic. This separation lets you change the email layout with little impact on order processing.

### 2.1. Which parts are dynamic data?

Suppose the order confirmation template needs these components:

| Component in the email | Data source | Handling suggestion |
| --- | --- | --- |
| Customer name | User profile | Escape as text when inserting into HTML |
| Order number | Order service | Choose a value that has been validated and contains no secret information |
| Product list | Order details | Convert to a suitable DTO to iterate in the template |
| Total amount | The application's pricing logic | Format by currency/locale **before** passing it into the template, or use an explicit formatter |
| Order view link | The application generates the link from a trusted domain | Check the scheme/host and parameters; do not trust arbitrary URLs |
| Logo and colors | Brand identity assets | Controlled static templates/resources |
| Support address | Application configuration | No need to put the SMTP password into the model |

A good template variable represents **meaning**, such as `customerName`, `orderLines`, or `orderUrl`, and should not carry client-supplied HTML structure such as `customerNameHtml`.

## 3. Which dependencies are needed in Spring Boot?

If you use Thymeleaf and Spring Mail, in the Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
~~~

In Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-thymeleaf</artifactId>
    </dependency>
</dependencies>
~~~

The examples assume the project already has a Spring Boot parent/BOM or an equivalent way of managing versions. Do not pin different versions for each library just to piece the examples together without first checking which Spring Boot version the project uses.

**Roles:**

- `spring-boot-starter-mail`: Spring Mail, Jakarta Mail, and the dependencies needed to create/send SMTP messages.
- `spring-boot-starter-thymeleaf`: the template engine together with the Spring Boot integration for loading and processing templates.

**Adding the web starter is not required** just to render HTML for email. A background mail-sending worker can also use the template engine without an HTTP controller. If the project already uses Thymeleaf for web pages, you can reuse the engine and the template infrastructure to the extent that the template organization and context are appropriate.

## 4. Organizing the template files

With the commonly encountered default configuration of Spring Boot + Thymeleaf, templates are looked up in `classpath:/templates/` with the `.html` suffix:

~~~text
src/
  main/
    java/
      com/example/mail/
        application/
          OrderMailService.java
          OrderMailData.java
        config/
          MailConfiguration.java
    resources/
      templates/
        mail/
          order-confirmation.html
          order-confirmation.txt
          account-welcome.html
      application.yml
~~~

In the example, `templates/mail/order-confirmation.html` can be rendered using the logical name `"mail/order-confirmation"`. The `order-confirmation.txt` file illustrates where to store a plain-text template if a resolver for text has been configured; **the default Thymeleaf auto-configuration for HTML does not mean it will automatically render every `.txt` file**. You can use a separate renderer or declare a resolver with the TEXT template mode.

Benefits of the `mail/` directory:

- Separates email templates from web page templates.
- Name them by **business action** rather than by a specific recipient.
- Makes it easy to add locales, versions, and shared components as the system grows.
- Allows previewing emails in the development environment with non-sensitive sample data.

### 4.1. Are templates entered by users?

In the commonly encountered architecture, **the template is a trusted resource controlled by the development team/content administrators**, while the variables passed in are business data that may contain untrusted input. You should not let public users submit an HTML/Thymeleaf expression and then ask the server to render it like a system template. A template engine has an expression language and may have more access privileges than a plain-text renderer.

If the product lets users manage their own templates, you need a permission model, expression restrictions, validation, a sandbox, or another rendering mechanism designed specifically for it; do not by default pass an untrusted template string into `SpringTemplateEngine.process(...)`.

## 5. Creating an HTML email template

Example `src/main/resources/templates/mail/order-confirmation.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Order confirmation</title>
</head>
<body style="margin:0; padding:24px; background:#f4f6f8; font-family:Arial,sans-serif;">
  <table role="presentation" cellpadding="0" cellspacing="0"
         style="max-width:600px; width:100%; margin:auto; background:#ffffff;">
    <tr>
      <td style="padding:28px; color:#263238;">
        <h1 style="font-size:22px; margin:0 0 18px;">Order confirmed</h1>

        <p>
          Hello
          <strong th:text="${customerName}">Customer</strong>,
        </p>

        <p>
          Order
          <strong th:text="${orderId}">A123</strong>
          has been recorded.
        </p>

        <table role="presentation" cellpadding="8" cellspacing="0"
               style="width:100%; border-collapse:collapse;">
          <tr>
            <th align="left">Product</th>
            <th align="right">Qty</th>
            <th align="right">Amount</th>
          </tr>
          <tr th:each="line : ${orderLines}">
            <td th:text="${line.name}">Product name</td>
            <td align="right" th:text="${line.quantity}">1</td>
            <td align="right" th:text="${line.priceText}">$100.00</td>
          </tr>
        </table>

        <p>
          <strong>Total:</strong>
          <span th:text="${totalText}">$100.00</span>
        </p>

        <p style="margin:24px 0;">
          <a th:href="${orderUrl}" href="https://example.com/orders"
             style="display:inline-block; padding:12px 20px; background:#1769aa; color:white; text-decoration:none;">
            View order
          </a>
        </p>

        <p th:if="${showSupport}">
          If you need help, please reply to this email.
        </p>
        <p style="color:#607d8b; font-size:12px;">
          This is an automated notification from our service.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>
~~~

This is **an HTML template for email**, not a web page rendered directly in the application's browser. The `th:*` attributes are processed only when Thymeleaf renders the template on the server side. After rendering, the recipient sees ordinary HTML; they do not need Thymeleaf.

### 5.1. The Thymeleaf expressions used

| Syntax | Function | Example |
| --- | --- | --- |
| `th:text="${customerName}"` | Puts data into the element's text content, with HTML escaping | Customer name |
| `th:href="${orderUrl}"` | Puts a value into the href attribute, processed appropriately for an HTML attribute | Order view link |
| `th:each="line : ${orderLines}"` | Repeats an element for each item in a list | The product lines |
| `th:if="${showSupport}"` | Includes the element in the output only when the condition matches | The contact instructions section |
| `${orderId}` | Retrieves a variable from the context | Order number |

When rendering, Thymeleaf replaces the necessary parts with values from the `Context`. The template does not load the order list from the database by itself; the data must be supplied by the application.

### 5.2. Why does HTML email often use tables and inline CSS?

Email clients do not behave like modern web browsers:

- Many clients restrict or strip JavaScript, forms, external CSS, and some selectors.
- Some clients handle CSS layout, margins, fonts, or dark mode differently.
- Images from external URLs may be blocked to protect privacy.
- Screen sizes, fonts, and mail viewing modes are very diverse.

For that reason, real-world HTML email usually uses **tables for the basic layout**, **inline CSS**, and a simple structure. Do not put dependencies such as the React runtime, JavaScript event handlers, login forms, or complex CSS into the email and then expect all clients to process it like a browser.

The email should have content that can be understood even when images do not load, colors change, or CSS is stripped.

## 6. Designing data specifically for email

You should not pass a JPA entity straight into the template and let the template freely access the entire data relationship graph. A **DTO dedicated to building the email** helps:

- define precisely what is allowed to appear in the email;
- avoid accessing lazy relationships outside a transaction;
- reduce leakage of unrelated information;
- make it easy to test sample data and null cases;
- allow formatting amounts/dates before rendering.

Java record example:

~~~java
package com.example.mail.application;

import java.net.URI;
import java.util.List;

public record OrderLineMailData(
        String name,
        int quantity,
        String priceText) {
}

public record OrderMailData(
        String recipient,
        String customerName,
        String orderId,
        String totalText,
        URI orderUrl,
        List<OrderLineMailData> orderLines,
        boolean showSupport) {
    public OrderMailData {
        orderLines = List.copyOf(orderLines);
    }
}
~~~

In a Java project, the two `public record` declarations above should be placed in **two separate files** matching their respective type names. The example puts them together here only to show the data structure. `List.copyOf` avoids retaining later changes to the source list; because the elements are records with value-like fields, the model is useful for requests sent through a queue or for testing.

`priceText` and `totalText` are **already formatted** values for display. The exact calculation of amounts still belongs to the business logic; use `BigDecimal` and appropriate currency rules, and do not recalculate in JavaScript inside the email or use floating-point numbers in the template.

### 6.1. Don't let the template make business decisions

For example, a template may choose to show or hide the support instructions paragraph through `showSupport`. But the template should not decide for itself whether a customer **is allowed to view the order**. Access rights must be controlled in the backend when creating the link and when the user opens the link; hiding a button in the email is not an authorization mechanism.

If the order contains sensitive data, put only the minimum amount of information into the email. The link can lead to a page that requires login instead of putting all payment details into the HTML.

## 7. Rendering HTML with Thymeleaf and then sending with JavaMailSender

In Spring Boot with the Thymeleaf starter, the application can usually inject a `SpringTemplateEngine` that is configured with a resolver for the templates.

~~~java
package com.example.mail.application;

import java.util.Locale;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.context.Context;
import org.thymeleaf.spring6.SpringTemplateEngine;

@Service
public class OrderMailService {
    private final JavaMailSender sender;
    private final SpringTemplateEngine templateEngine;
    private final String from;
    private final String replyTo;

    public OrderMailService(
            JavaMailSender sender,
            SpringTemplateEngine templateEngine,
            @Value("${app.mail.from}") String from,
            @Value("${app.mail.reply-to}") String replyTo) {
        this.sender = sender;
        this.templateEngine = templateEngine;
        this.from = from;
        this.replyTo = replyTo;
    }

    public void sendConfirmation(OrderMailData data)
            throws MessagingException {
        // The DTO must have been created and validated earlier in the business layer.
        Context context = new Context(Locale.forLanguageTag("en-US"));
        context.setVariable("customerName", data.customerName());
        context.setVariable("orderId", data.orderId());
        context.setVariable("orderLines", data.orderLines());
        context.setVariable("totalText", data.totalText());
        context.setVariable("orderUrl", data.orderUrl().toString());
        context.setVariable("showSupport", data.showSupport());

        String html = templateEngine.process(
                "mail/order-confirmation",
                context);

        String plainText = """
                Hello %s,

                Order %s has been recorded.
                Total: %s
                View order: %s
                """.formatted(
                data.customerName(),
                data.orderId(),
                data.totalText(),
                data.orderUrl());

        MimeMessage mime = sender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom(from);
        helper.setReplyTo(replyTo);
        helper.setTo(data.recipient());
        helper.setSubject("Order confirmation " + data.orderId());
        helper.setText(plainText, html);

        sender.send(mime);
    }
}
~~~

Explanation of the steps:

1. **Create the `Context`:** each send has its own context for content and locale.
2. **Put the variables into the context:** the variable names must match the expressions in the HTML file.
3. **Render:** `templateEngine.process("mail/order-confirmation", context)` reads the template and produces the final HTML string.
4. **Create the MIME message:** `JavaMailSender.createMimeMessage()` creates the mail object.
5. **Specify the charset:** `MimeMessageHelper(..., "UTF-8")` helps handle Vietnamese characters correctly in the message.
6. **Attach text and HTML:** `setText(plainText, html)` lets the email client choose the appropriate version.
7. **Send:** `sender.send(mime)` submits the email to the configured transport.

For **Spring Boot 3.x / Spring Framework 6**, the Jakarta Mail imports use `jakarta.mail.*` and Thymeleaf's Spring 6 integration has `org.thymeleaf.spring6.SpringTemplateEngine`. In projects using an older generation of Spring Boot/Spring Framework, the packages may differ; do not mix the old `javax.mail` namespaces with the new `jakarta.mail`.

### 7.1. Why not use SimpleMailMessage?

`SimpleMailMessage` is meant for **plain text**; putting an HTML string into `setText(...)` does not make the email client render the tags:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setText("<h1>Hello</h1>"); // Still plain text.
~~~

To send HTML, we need a `MimeMessage` and a `MimeMessageHelper` (or the Jakarta Mail API directly), with the body declared as type `text/html`.

### 7.2. Is multipart needed?

In the example above, the helper is created with the parameter `true`, which enables multipart support:

~~~java
new MimeMessageHelper(mime, true, "UTF-8");
~~~

This is convenient when there is **plain text + HTML**, and it extends to attachments or inline images. For an email with only HTML and no attachments, you can use:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(mime, false, "UTF-8");
helper.setText(html, true);
~~~

`setText(html, true)` indicates that this is HTML content. With the `setText(plainText, htmlText)` overload, Spring Mail creates alternative representations for the client to choose from. The detailed MIME structure may differ depending on the multipart mode and the library.

Do not equate “HTML has been rendered with Thymeleaf” with “HTML MIME has been sent”: Thymeleaf only produces a string. When building the `MimeMessage`, you must declare the appropriate content.

## 8. Configuring the mail sender and application settings

Example `application.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM:no-reply@company.example}
    reply-to: ${MAIL_REPLY_TO:support@company.example}
~~~

- `spring.mail.*` is the SMTP configuration that Spring Boot can use to initialize the mail sender.
- `app.mail.*` are properties **defined by the application**; the code must read them and set the headers through `MimeMessageHelper`.
- Passwords, API keys, or OAuth tokens must be provided through the runtime environment/secret manager, not hardcoded in Java, HTML templates, or committed to the repository.
- The example uses **STARTTLS on the commonly used port 587**; a provider that uses TLS from the start over another port needs a corresponding transport configuration.

**The template should not know the SMTP password.** By nature, a template is text displayed to the recipient; there is no reason to put secrets into the context. When debugging, avoid logging the entire context if it contains emails, tokens, or customer data.

### 8.1. Thymeleaf configuration

In a Spring Boot application using the Thymeleaf starter, commonly seen properties:

~~~yaml
spring:
  thymeleaf:
    prefix: classpath:/templates/
    suffix: .html
    mode: HTML
    encoding: UTF-8
    cache: true
~~~

This is a reference configuration: the values above are close to the common defaults. **Template caching** is usually useful in production; when developing the email UI, you can turn off the cache via the local environment configuration to see changes easily. Do not change the cache policy arbitrarily to fix data-not-updating bugs: data is passed through a separate `Context` for each render, while the cache mainly concerns how templates are loaded/parsed.

If the application also uses Thymeleaf for the web, consider the scope of changes to `spring.thymeleaf.*`, because it can affect web page templates as well. When mail requirements differ greatly, you can configure a **separate template resolver** for email, instead of changing the shared resolver in unexpected ways.

## 9. Escaping: the important boundary when inserting data

Not all data coming from the application is trustworthy. Customer names, order notes, product names, or strings entered through forms may contain HTML characters and even content that tries to alter the email's appearance.

Suppose:

~~~text
customerName = "An <Admin> & Co"
~~~

When inserting with:

~~~html
<span th:text="${customerName}">Name</span>
~~~

Thymeleaf will escape the necessary characters so that the resulting HTML represents **text**:

~~~html
<span>An &lt;Admin&gt; &amp; Co</span>
~~~

The reader sees the corresponding content, rather than a new `<Admin>` tag. This is the reason to use `th:text` for people's names, product names, transaction codes, and data meant only for displaying text.

### 9.1. Avoid `th:utext` with untrusted data

Thymeleaf has `th:utext` to insert **unescaped text**:

~~~html
<!-- Use only with HTML that has been controlled and safely processed. -->
<div th:utext="${trustedHtmlFragment}"></div>
~~~

If you use `th:utext` with a `customerNote` entered by a user, the data may be treated as **HTML markup** instead of text. Email clients usually filter some dangerous HTML, but **you must not rely on the client's filter to ensure safety**. Malicious content can still create phishing links, misleading layouts, or exceed security assumptions.

If the business truly needs an HTML fragment from a content editor, use an **allowlist-based sanitize** process and control who is permitted to create that content. Only escape output according to context and only allow the necessary markup; do not take “a template engine was used” as proof that every HTML string is safe.

### 9.2. Text escaping is different from URL validation

The template has:

~~~html
<a th:href="${orderUrl}">View order</a>
~~~

The template engine helps place the value into an HTML attribute with the correct syntax; but it **does not by itself guarantee that the URL address is somewhere the user should go**. A user-controlled path can send the recipient to a phishing website even though the attribute has been escaped.

For transactional links:

1. Generate the URL from the **configured and controlled application base URL**, instead of accepting an arbitrary URL from the client.
2. Use **HTTPS** for the production environment as appropriate; check the allowed hostname/domain.
3. Encode path segments and query parameters according to their position when building the URI.
4. Avoid putting long-lived tokens or secret data into the URL; verification/password-reset links need a random token, a clear scope, and a short expiry.
5. When the user opens the link, the backend must check access rights; a valid path in the email **does not by itself create permission**.

Example of generating a URL from a trusted domain instead of trusting input:

~~~java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

URI orderUrl = UriComponentsBuilder
        .fromUriString("https://app.company.example")
        .pathSegment("orders", orderId)
        .build()
        .encode()
        .toUri();
~~~

This example uses Spring Web's `UriComponentsBuilder`, so the appropriate Spring Web dependency must be present if the application does not already have it. If the mail module deliberately does not depend on Spring Web, you can build the URI with a standard encoding tool or accept a URI that has already been created and checked by the application layer. The domain `app.company.example` is only for illustration.

### 9.3. Avoid header injection

Values used in `Subject`, `From`, or `To` must not be created by assembling raw SMTP/MIME headers from input. Use the Spring/Jakarta Mail setters and validate the input strings, especially CR/LF control characters, the number of recipients, and length.

Content in the HTML being escaped **does not mean the Subject or the addresses have been checked too**. Headers and body are two different surfaces.

## 10. Don't let the template access the database or call external services on its own

A poor design is to pass the entire `OrderEntity` into the context and let the template access every property and relationship:

~~~java
// Do not do this by default:
context.setVariable("order", orderEntity);
~~~

Risks:

- The template can access sensitive fields beyond what is needed for display.
- If `orderEntity` has a lazy collection, rendering outside a transaction can cause errors.
- The template may depend on the ORM, making the mail UI hard to separate from the database.
- Data may change between renders without a clear snapshot policy.

Instead, the business layer creates `OrderMailData` with the selected fields and then passes it to the template. In the template, use only the DTO's properties. A template should **format and present**, not be a place to look up prices, check payment status, or apply authorization policy.

If sending mail through a queue, consider **snapshotting the data when enqueuing** or storing an explicit version of the data/template. Having the worker use the latest information may be valid in some problems, but it should not be random behavior caused by data access happening late.

## 11. Plain text and HTML are two versions of the same email

Not every recipient displays HTML:

- A client may be configured to view plain text only.
- Some filtering systems and email gateways process content differently.
- HTML may be truncated, CSS may be unsupported, or images may be blocked.
- Recipients may need access through assistive technology or have a low-bandwidth environment.

Therefore, an important transactional email should have a **plain-text version that provides the same core information** as the HTML.

Example:

~~~text
Hello An Nguyen,

Order A123 has been recorded.

Details:
- Java Book x 1: $200.00
- Shipping fee: $20.00

Total: $220.00

View order:
https://app.company.example/orders/A123

If you need help, please reply to this email.
~~~

The HTML may have a “View order” button, but the text should contain the **full URL**. If the HTML contains important information that the plain text lacks, people viewing the text may be missing data.

In Spring Mail:

~~~java
helper.setText(plainText, html);
~~~

This API expresses that **the two parts are alternatives** in MIME, not content sent one after the other for the recipient to read twice. Usually the email client will choose the appropriate representation.

### 11.1. A separate template for the text version

At large scale, plain text can also be generated from a text-specific template, for example:

~~~text
Hello [[${customerName}]],

Order [[${orderId}]] has been recorded.
Total: [[${totalText}]]
View details: [[${orderUrl}]]
~~~

This illustrates Thymeleaf's **text inlining** syntax when processed in the appropriate mode. Do not expect a `.txt` file to work automatically just because the Thymeleaf starter has been added: you need to configure a **TEXT template resolver/mode** and choose the correct template name, or use another way of rendering text. You also need to use validated data and avoid concatenating parts containing control characters into where headers are created.

For simple mail, a Java formatter that produces plain text from a DTO can be clear enough; with many languages, a set of HTML + text templates per locale is usually easier to maintain.

## 12. Images in HTML email: URL and CID

There are two common ways to put a logo into an email:

### 12.1. Image from an external URL

~~~html
<img src="https://assets.company.example/logo.png"
     alt="Company logo" width="120">
~~~

Advantages: the email is smaller, and a CDN can be used. Disadvantages: the client may block remote images, the link may expire, or the image source may stop working. The image URL should not contain secrets or unnecessary recipient data.

### 12.2. Inline image via Content-ID

In the template:

~~~html
<img src="cid:company-logo" alt="Company logo" width="120">
~~~

When building the MIME:

~~~java
MimeMessage mime = sender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("no-reply@company.example");
helper.setTo("customer@example.net");
helper.setSubject("Welcome");

String html = "<html><body><img src=\"cid:company-logo\" alt=\"Logo\">" +
              "<p>Welcome!</p></body></html>";

// Set the text before adding inline resources.
helper.setText("Welcome!", html);
helper.addInline(
        "company-logo",
        new org.springframework.core.io.ClassPathResource("mail/logo.png"),
        "image/png"
);

sender.send(mime);
~~~

The resource `src/main/resources/mail/logo.png` must actually exist on the classpath. `company-logo` in `addInline(...)` must match the part after `cid:` in the HTML. `MimeMessageHelper` packages the image as a related MIME part; some clients may still display the image as an attachment or block the image due to security policies.

The logo is a presentation resource; do not put mandatory information (confirmation code, amount, security instructions) only in an image.

## 13. Multi-language support, currency formatting, and date/time

An application may send mail to users of many locales. An HTML template should not guess the language or timezone from the server:

~~~java
Locale locale = Locale.forLanguageTag("en-US");
Context context = new Context(locale);
~~~

### 13.1. Choosing the right locale

A common rule:

1. If the user has chosen a language in their profile, use that language.
2. If not, use the product's or organization's default locale.
3. State clearly the language used at the email content level; avoid mixing Vietnamese and English depending on each variable.

Example at the organization level:

~~~text
templates/mail/
  order-confirmation-vi.html
  order-confirmation-en.html
~~~

The application can choose the template by locale; you can also use Thymeleaf message bundles and `#{...}` to internationalize static strings. You should settle on one approach so that an email does not mix translations that are hard to control.

### 13.2. Formatting amounts by business rules/locale

If the total amount value is a `BigDecimal`, do not insert Java's debug-style form directly:

~~~text
220000.00
~~~

You should display it according to the appropriate currency:

~~~text
$220.00
~~~

In the application, you can use `NumberFormat.getCurrencyInstance(locale)` with the exact currency or a formatter defined separately according to product requirements. Do not assume every locale has the same number of decimal digits, separators, or currency symbols.

### 13.3. Time must have a clear timezone

The order creation time can be stored as an `Instant` or `OffsetDateTime`. When rendering the email, you should format it according to a timezone determined from the recipient or business configuration:

~~~text
Order date: 12/11/2026 14:30 (GMT+7)
~~~

If you display “14:30” without a clear timezone, the email may cause misunderstanding in a cross-border system. The template should only receive an already formatted time string or a value with a clear formatting rule.

## 14. Separating content data from operational data

The template context may contain:

~~~text
customerName
orderId
orderLines
totalText
orderUrl
showSupport
~~~

But it **should not contain**:

~~~text
smtpPassword
smtpApiKey
dbPassword
internalAccessToken
fullUserEntity
creditCardNumber
privateSigningKey
~~~

To create an email, the template needs only display data, not access to the sending system. Secret values belong in the secret manager and runtime configuration; do not pass them through a controller, event payload, or job just because “the template might need them”.

### 14.1. Queue and rendered content

When sending asynchronously, you need to decide:

**Option A — render before enqueuing:** the producer creates the HTML and plain-text strings and then stores a snapshot in the job. When the worker runs, the content has been fixed, but the payload is large and may contain a lot of personal information that needs protection in the broker/outbox.

**Option B — enqueue the data and template version:** the producer stores the captured DTO together with the template version identifier; the worker renders at send time. The payload is small and easy to track, but the data/template version must be kept stable so that a retry does not change the content unintentionally.

| Criterion | Render before enqueue | Render in the worker |
| --- | --- | --- |
| When the HTML is determined | Producer | Worker |
| Queue payload size | Can be large | Usually smaller |
| Content stability when the template is edited | High if the complete HTML is stored | Need to pin the template version |
| Sensitive data in the queue | May contain the full HTML | May still contain business data |
| Ability to retry with the same content | Use the stored snapshot | Use the data snapshot + template version |

Do not enqueue only `orderId` and then let the worker read the “latest data” and use the “latest template” if the business requires the email to preserve the information as of the time the request was created. When the order changes before sending, that behavior can produce an email whose content does not match the original event.

## 15. Testing templates and generated emails

The functionality needs to be tested at **two different boundaries**:

1. **Render:** the application data has been inserted into the template as HTML with the correct meaning, escaped, and with missing values handled.
2. **Send:** the MIME message is created correctly from the HTML/text, and the addresses and headers are set correctly; this can be tested with mocks or a test SMTP server.

### 15.1. Testing the renderer in isolation

Example when a `SpringTemplateEngine` is available with an appropriate resolver configured:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.thymeleaf.context.Context;
import org.thymeleaf.spring6.SpringTemplateEngine;

class OrderMailTemplateTest {
    private final SpringTemplateEngine engine;

    OrderMailTemplateTest(SpringTemplateEngine engine) {
        this.engine = engine;
    }

    @Test
    void escapesCustomerNameInHtml() {
        Context context = new Context(Locale.forLanguageTag("en-US"));
        context.setVariable("customerName", "An <Admin>");
        context.setVariable("orderId", "A123");
        context.setVariable("orderLines", java.util.List.of());
        context.setVariable("totalText", "$220.00");
        context.setVariable("orderUrl", "https://app.company.example/orders/A123");
        context.setVariable("showSupport", false);

        String html = engine.process("mail/order-confirmation", context);

        assertTrue(html.contains("An &lt;Admin&gt;"));
        assertFalse(html.contains("<Admin>"));
        assertTrue(html.contains("A123"));
    }
}
~~~

This is a snippet that **illustrates the body of a test** when a `SpringTemplateEngine` has been provided; to run it with JUnit Jupiter, the project needs to create the test instance through the Spring test context or set up the engine in `@BeforeEach`/the constructor according to the existing test infrastructure. Do not take this example to mean that JUnit injects the constructor by itself just because there is a parameter of type `SpringTemplateEngine`.

What is worth checking: data in variables does not unexpectedly become HTML markup; empty lists/missing information are rendered according to policy; the final links use the correct permitted domain.

### 15.2. Testing the outgoing message

You can mock `JavaMailSender` to confirm that the service calls `createMimeMessage()` and `send(...)` with a suitable `MimeMessage`. Because MIME has many parts and encodings, deeper checks should look at the actual MIME content rather than searching for a substring in a Java object that has not been serialized.

For integration tests, you can configure a simulated SMTP such as **Mailpit** or **GreenMail**. The procedure:

1. Start the application with the SMTP test server, without using production credentials.
2. Create a test DTO with a Unicode name and a valid URL.
3. Call the email-sending service.
4. Inspect the message source/`.eml`: `Content-Type`, `charset`, the `text/plain` and `text/html` parts, and the `From`, `To`, `Subject` headers.
5. View the email preview UI; check images, buttons, spacing, Vietnamese text, and the case where CSS/images do not load.

Testing through a simulated SMTP **does not confirm the email will reach the Inbox** when sending through a production provider. That is a separate operations and delivery-tracking problem.

### 15.3. Sample data sets to have

| Test scenario | Purpose |
| --- | --- |
| Normal name with Vietnamese diacritics | Check UTF-8 and font display |
| Name containing `<`, `>`, `&`, or quotes | Check the template's escaping |
| Empty product list | See whether the layout needs a fallback message |
| Long list | See whether the table overflows on mobile or in the email client |
| Very long product name | See line wrapping and table width |
| Large total, different currency | Check the formatter by locale |
| Invalid link or domain outside the allowlist | Ensure the application rejects it before rendering |
| HTML without images/CSS loaded | Core information is still readable |
| Email address or Subject with invalid characters | Validation at the message-building layer |

## 16. Common problems

| Symptom | Possible cause | Approach |
| --- | --- | --- |
| The recipient sees the literal `<h1>...` | HTML was put into `SimpleMailMessage` or `setText(html, false)` | Use `MimeMessageHelper.setText(html, true)` or text + HTML |
| The email contains an unreplaced `${customerName}` or `th:text` | The template was not processed through Thymeleaf | Call `templateEngine.process(...)` and send the rendered result |
| Template not found | Wrong logical name, prefix/suffix, or the file is not on the classpath | Check `templates/mail/...` and the resolver |
| Data is `null` or does not appear | The context variable name differs from the template, or the DTO is missing data | Synchronize the model contract and the template, handle null explicitly |
| Customer name with diacritics turns into garbled characters | Charset/header or encoding is unsuitable | UTF-8 in the helper and template, inspect the raw MIME |
| HTML displays differently between clients | CSS/layout is not uniformly supported | Simple email layout, inline CSS, test important clients |
| Images do not display | The remote image is blocked or the CID/Content-ID does not match | Use alt text; check the URL or `addInline` |
| A link leads to the wrong domain | An uncontrolled URL from input is used | Generate links with a trusted base URL and check scheme/host |
| User data becomes HTML markup | String concatenation or `th:utext` with untrusted input | Use `th:text`, sanitize permitted HTML content |
| The HTML body is correct but people viewing only text are missing information | No plain-text alternative was created, or the content is out of sync | Create the text version from the same DTO |
| The email has HTML but SMTP rejects it | Send error, auth, policy, size, or network | Separate render errors from transport errors; check SMTP/provider |
| Old template after deploy | Template cache, or the application has not loaded the new build | Check the deployment method and the cache policy per environment |
| A retried email has changed content | The worker reads the latest data/template | Capture the data and pin the template version, or store the HTML snapshot |

### 16.1. Distinguishing render errors from send errors

The two kinds of errors lie in two stages:

~~~text
DTO -> TemplateEngine.process(...) -> html
         |
         +-- template / variable / expression / resolver error

html -> MimeMessageHelper -> JavaMailSender.send(...)
                              |
                              +-- SMTP auth / network / policy / timeout
~~~

If the template is not found, the error occurs **before** the SMTP connection is opened. If the SMTP credential is wrong, rendering can still succeed, but sending will fail.

In an asynchronous sending application, you should record states such as `RENDER_FAILED`, `SUBMISSION_FAILED`, and `SUBMITTED` if the system needs to coordinate work. Do not retry indefinitely errors caused by wrong template syntax or missing required variables; those errors usually require fixing the configuration/content or the data.

## 17. Process for rolling out a new email template

When there is a requirement to “send an order confirmation email with a product table and a view-details button”, you can proceed as follows:

1. **Finalize the data contract:** the email needs the name, order number, product lines, total amount, and URL. Identify required fields, optional fields, and the data sources.
2. **Create a dedicated DTO:** include only data that is permitted to be sent; format money/dates by locale.
3. **Design the HTML template:** simple, easy to read, with alt text, inline CSS, and meaningful links.
4. **Put the data into the context:** use `th:text`, `th:each`, `th:if`, and `th:href` in the right context.
5. **Block dangerous data:** do not use `th:utext` for free-form input; check the URL domain and the recipient.
6. **Create the plain-text version:** the same core information, with the full URL.
7. **Build the MIME:** use `MimeMessageHelper` with UTF-8, set From/To/Reply-To/Subject and `setText(plainText, html)`.
8. **Internal test send:** view the HTML preview and the raw email through an SMTP test server.
9. **Move into the real sending process:** monitor submission, SMTP errors, retries, bounces, and sending limits.
10. **Manage template changes:** versioning, review, sample data, and a compatibility policy for pending jobs.

This is a process that can scale from a simple notification up to an email module with many templates and many languages without forcing the SMTP logic to know the layout of each email.

## 18. A combined scenario: order confirmation per recipient

Suppose the application handles two different orders:

~~~text
Order A123:
  recipient = an@example.net
  customerName = An Nguyen
  orderId = A123
  totalText = $220.00

Order B456:
  recipient = binh@example.net
  customerName = Binh Tran
  orderId = B456
  totalText = $1,250.00
~~~

You do not need two HTML files. The application uses **the same template** but creates **two separate `Context`s**:

~~~text
order-confirmation.html
    |
    +-- Context A --> Rendered HTML A --> MimeMessage A --> an@example.net
    |
    +-- Context B --> Rendered HTML B --> MimeMessage B --> binh@example.net
~~~

For each send:

- Data A must not leak into message B.
- `MimeMessage` and `MimeMessageHelper` are newly created, and no mutable objects are shared between threads.
- The A/B links are generated for the correct order, and access rights must be checked in the application when the recipient opens the link.
- The Subject and the plain-text version are built from the same DTO.
- The SMTP sender can be shared as a Spring bean, but the messages are built independently.

The key point of **“HTML templates and data inserted from the application”** is not just the `th:text` syntax. It is a design boundary: **data is determined and controlled at the business layer; the template turns data into safely displayable content; Spring Mail packages the result into MIME and sends it over SMTP**. When these three parts are kept separate, email is easier to maintain, reduces the risk of unintended markup injection, is easier to test, and can scale to many templates/locales without rewriting the sending mechanism.

### References

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessage`, and `MimeMessageHelper`.
- **Spring Boot Reference — Sending Email:** `spring-boot-starter-mail`, `spring.mail.*`, and SMTP configuration.
- **Spring Boot Reference — Thymeleaf:** template resolver, `spring.thymeleaf.*`, and the auto-configuration mechanism.
- **Thymeleaf Documentation — Standard Dialect:** `th:text`, `th:each`, `th:if`, `th:href`, escaping, and text inlining.
- **RFC 2045–2049 — MIME:** `text/plain`, `text/html`, `multipart/alternative`, and the mechanism for representing email content.
