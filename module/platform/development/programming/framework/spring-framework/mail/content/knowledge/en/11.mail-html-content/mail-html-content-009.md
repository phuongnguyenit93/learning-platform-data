# Template engines and the boundary between data and markup

HTML email lets a Spring application send notifications with layout, colors, action buttons, and personalized content. Instead of concatenating many HTML strings in Java, applications usually use a **template engine**: a template file containing the HTML structure and placeholders replaced with data when sending the message.

The ability to insert dynamic data also creates an important boundary:

> **Markup is the presentation structure designed and controlled by the application; data is the value fed into that structure, which may come from users or other systems.**

If the application accidentally treats untrusted data as markup, a customer name or order note can turn into HTML tags, spoofed links, or content that alters the message layout. Conversely, if all content is processed as plain text, intentionally designed HTML snippets can appear verbatim in the mail client.

In **Spring Framework Mail**, a common architecture is **Thymeleaf** (or an equivalent template engine) building the HTML, and then **`JavaMailSender`** and **`MimeMessageHelper`** packaging that HTML into a MIME message. This lesson explains the boundary between data and markup, context-aware escaping, Spring Boot/Thymeleaf examples, and common mistakes.

## 1. What role does a template engine play in HTML email?

A template engine takes a **template** and a **data model**, then produces the output string:

```text
Business event: order confirmed
               |
               v
   Build a strongly typed mail model
   - customerName
   - orderCode
   - orderUrl
               |
               v
     Template engine (e.g., Thymeleaf)
       + HTML template written by the application
       + data from the mail model
               |
               v
     Rendered HTML string
               |
               v
     MimeMessageHelper.setText(..., html)
               |
               v
      Jakarta Mail creates MIME message
               |
               v
          JavaMailSender
               |
               v
     SMTP server -> mail client
```

The two blocks of work should not be mixed:

1. **Render:** the template engine decides which characters or HTML structure appear in the message body from the template and data.
2. **Send:** Spring Mail/Jakarta Mail packages the content as MIME, sets sender/recipient and charset, and delivers the message over SMTP.

`MimeMessageHelper` **is not a template engine**: it can declare a body part as HTML, yet it does not decide on its own whether `customerName` is HTML-escaped. The template engine also **does not send mail**; the rendered result must be put into a message and handed to the sender.

### When should you use a template engine?

- Many emails share a common header, footer, logo, and layout rules.
- Content changes by order data, user, or language.
- HTML has conditional display (for example, with or without a discount code).
- Email templates need to be maintained separately from business code.
- You want a consistent convention for escaping dynamic values.

For a very simple text email, using `SimpleMailMessage` may be enough. But when **HTML and safe data binding** are needed, a template engine usually makes the boundary between data and structure clearer.

## 2. Understanding the boundary: what is markup, what is data?

Consider a welcome email containing the user's name.

**Markup designed by the application:**

```html
<p>Hello, <strong>...</strong>!</p>
<p>Thank you for registering.</p>
```

**Data coming from the system:**

```text
customerName = "An Nguyen"
```

Desired result:

```html
<p>Hello, <strong>An Nguyen</strong>!</p>
<p>Thank you for registering.</p>
```

In the normal case, the two approaches can look the same:

```java
// Do not concatenate arbitrary data directly into HTML.
String html = "<p>Hello, <strong>" + customerName
        + "</strong>!</p>";
```

However, if `customerName` contains special HTML characters:

```text
customerName = "<b>VIP Customer</b> & friends"
```

With raw string concatenation, the text above can become **real markup**. The `<b>` tag is interpreted as HTML structure instead of part of the user's name. Data has crossed the boundary the application needs to protect.

The right result if you want to display the **literal value** is:

```html
<p>Hello, <strong>&lt;b&gt;VIP Customer&lt;/b&gt; &amp; friends</strong>!</p>
```

The mail client displays the name as `<b>VIP Customer</b> & friends` in text form, without turning the user-entered `<b>` into a new tag.

**Rule:** data does not automatically become HTML code just because it contains `<`, `>`, or quotes. The template decides the structure, while dynamic values must be inserted using an operation suited to the **HTML context**.

## 3. HTML escaping: the basic protection mechanism

**HTML escaping** converts characters with special meaning in HTML into entity form so they are displayed as data:

| Character in data | Common HTML representation | Why handle it? |
| --- | --- | --- |
| `&` | `&amp;` | Avoid being interpreted as the start of an HTML entity |
| `<` | `&lt;` | Avoid starting an HTML tag |
| `>` | `&gt;` | Avoid closing a tag unexpectedly |
| `"` | `&quot;` | Needs attention inside double-quoted attributes |
| `'` | `&#39;` or a suitable representation | Needs attention inside single-quoted attributes |

Specific entity names can vary between escapers, as long as when HTML is parsed they preserve the intended text meaning. Applications usually **do not need to replace each character manually**; let the template engine perform context-appropriate escaping.

### Escaping differs from validation and sanitization

These three activities solve different problems:

- **Validation:** does the data satisfy business conditions? For example, does the order code match the format, does the link use HTTPS and belong to an allowed domain?
- **Escaping/output encoding:** when inserting data into HTML, how should characters be represented so they do not become markup syntax?
- **Sanitization:** if you genuinely accept **HTML supplied by an external source**, keep only a permitted set of tags/attributes/protocols and strip the dangerous parts.

Example:

```text
Input:  "<strong>Hello</strong>"

Escaped as text:
  "&lt;strong&gt;Hello&lt;/strong&gt;"
  -> Displays literal text <strong>Hello</strong>

Sanitized as an allowed HTML fragment:
  "<strong>Hello</strong>"
  -> Displays the word Hello in bold
```

The two results serve **two different product intents**. Do not choose raw HTML handling just because you want to “preserve formatting” without a markup-allowance policy.

### Be careful with double escaping

Suppose the application HTML-escapes the name itself:

```text
Input:       A & B
Manual:      A &amp; B
```

If you then pass the value `A &amp; B` into a template operation that **escapes automatically**, the result may be:

```html
A &amp;amp; B
```

The mail client will display `A &amp; B` instead of `A & B`. Therefore, pass the **business-validated original value** to a single context-appropriate template escape operation, instead of encoding beforehand and then encoding a second time.

## 4. Thymeleaf: `th:text` and `th:utext` are different

Thymeleaf is a popular template engine in Spring applications. When rendering HTML:

- **`th:text`:** inserts content as **escaped text**; the value is processed so it does not become HTML markup.
- **`th:utext`:** inserts content as **unescaped text**; the string may be interpreted as HTML markup.

Template example:

```html
<p>
  Hello,
  <span th:text="${customerName}">Customer</span>
</p>
```

Model:

```java
context.setVariable(
        "customerName",
        "<strong>New user</strong>"
);
```

Thymeleaf with `th:text` inserts the value at `span`'s position **as escaped text**. An equivalent HTML snippet:

```html
<span>&lt;strong&gt;New user&lt;/strong&gt;</span>
```

Meanwhile:

```html
<span th:utext="${customerName}">Customer</span>
```

can put the string `<strong>New user</strong>` directly into the output, turning the `strong` tag into markup.

### Why is `th:utext` dangerous with external data?

If a note field or user name is passed through `th:utext`, a user can supply HTML to break the layout, insert spoofed links, tracking images, or unwanted content. Some mail clients filter scripts and dangerous HTML, yet **you must not rely on mail client filtering to protect email content**.

Example of **what not to do**:

```html
<!-- UNSAFE if customerNote is entered by a user or external source -->
<div th:utext="${customerNote}"></div>
```

What to do when you only need to display a text note:

```html
<p th:text="${customerNote}">Order note</p>
```

If you truly must support rich text:

1. Clearly define which markup elements are allowed.
2. Use a trusted HTML sanitizer configured with a **tag/attribute/protocol allowlist** for the email context.
3. Strip scripts, event handlers, iframes, dangerous URLs, and disallowed CSS.
4. Use raw/unescaped output only for the **result already sanitized** under that policy.
5. Note that sanitization and HTML email compatibility still need to be maintained as systems or libraries change.

For most transactional emails, **there is no need for users to supply HTML**; text data through `th:text` is the simpler and lower-risk option.

## 5. Escaping must depend on where the data is inserted

There is no single “escape everything” operation that works correctly for all situations. A variable may be inserted into:

1. Text content between two HTML tags.
2. Attribute values such as `title`, `alt`, or `href`.
3. A link's destination URL.
4. CSS or the `style` attribute.
5. A markup fragment permitted by policy.

Each case requires **distinguishing fixed structure from dynamic values**.

### 5.1. Text node — use escaped text

```html
<p>Order code: <strong th:text="${orderCode}">ORD-001</strong></p>
```

When `orderCode` is data, Thymeleaf inserts it as text, not as HTML tags.

### 5.2. HTML attribute — use the template's attribute-setting mechanism

```html
<img src="cid:brandLogo"
     th:alt="${companyDisplayName}"
     width="120"
     height="40"/>
```

`th:alt` sets the attribute value and handles special characters in the way the template engine supports. Do not concatenate manually:

```java
// Do not assemble attributes with uncontrolled data.
String img = "<img alt=\"" + companyDisplayName + "\" ...>";
```

A display name containing quotes or special characters should not be allowed to break attribute syntax.

### 5.3. URL in `href` — escaping is not enough

This is an important boundary:

```html
<a th:href="${orderUrl}">View order</a>
```

The template engine can escape the attribute value syntactically, **yet a URL string can still point to an unsafe destination**. For example, if `orderUrl` is taken straight from a request and contains a spoofed host or disallowed scheme, HTML-escaping quotes **does not turn that URL into a safe URL**.

Therefore, for links in email:

- Prefer building URLs from a **system-managed base URL**, not from arbitrary user values.
- Allow only schemes with a valid purpose; for application access buttons, **HTTPS** is usually required.
- Check the host/domain against a trusted list when source data can influence the destination.
- Encode each part of the URL (path segment, query parameter) with a proper URI builder when they contain dynamic values.
- State the button's display text transparently, without masking a URL leading to an unfamiliar domain.

Structurally safe example with a typed ID:

```java
UUID orderId = /* determined order ID */;

// Base URL owned by the application; orderId has UUID format.
String orderUrl = "https://app.example.org/orders/" + orderId;
context.setVariable("orderUrl", orderUrl);
```

This is an illustrative URL. In a real deployment, the hostname must be configured/controlled per environment and ensure the recipient has permission to access the order; **knowing the link does not grant access rights by itself**.

### 5.4. CSS or `style` — do not pass free-form CSS from users

HTML email often uses inline CSS because many mail clients have limited CSS support. However, inserting an untrusted string into the `style` attribute can also break layout or create unwanted resource references.

Do not:

```html
<div th:style="${userProvidedCss}">Content</div>
```

Instead, choose between a few **fixed and controlled** styles:

```html
<p th:style="${isUrgent}
          ? 'color: #b42318; font-weight: bold;'
          : 'color: #344054;'">
  Notification
</p>
```

In this example, `isUrgent` is a boolean determined by business logic; the two CSS strings are written by the application. Do not pass an arbitrary CSS snippet from external data into the template.

### 5.5. JavaScript is not how to build interactivity in email

Do not design HTML email around `<script>`, event handlers like `onclick`, or browser mechanisms that mail clients may block. Proper email usually uses **HTTPS links** leading to a website or application where the user's action is authenticated and checked for permissions.

A template engine does not turn HTML email into a full interactive web page.

## 6. The data boundary is not only in customer names

Treat all variables passed to a template as **data**, unless they are genuinely markup content owned and controlled by the application:

| Data field | Possible source | How to put into email |
| --- | --- | --- |
| `customerName` | User profile | `th:text`, length limit |
| `orderCode` | Database | `th:text`, explicit formatting |
| `productName` | Product catalog, partner data | `th:text`, do not treat as HTML |
| `customerNote` | User-entered | `th:text`; do not use `th:utext` directly |
| `priceLabel` | Currency formatting logic | `th:text` after formatting |
| `orderUrl` | URL built from trusted domain and ID | `th:href` with controlled URL |
| `buttonLabel` | Application- or localization-supplied string | `th:text` |
| `statusColor` | Application presentation rules | Enum/boolean mapped to fixed CSS |
| `trackingId` | Business correlation code | Include only if needed, avoid exposing sensitive data |

Even data “from the database” is not automatically trusted for raw HTML rendering. A field may have been entered by a user and saved earlier. **Storing in the database does not turn it into safe markup**.

### Business data should be strongly typed

Example of a model:

```java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderMailData(
        UUID orderId,
        String orderCode,
        String customerName,
        BigDecimal totalAmount
) {}
```

Giving data explicit types helps the business layer restrict sources and states. The template receives only selected fields, instead of passing an entire entity containing passwords, tokens, internal addresses, or data not meant for the recipient.

Do not attach an entire user entity to the template context just because doing so is convenient. **Data minimization** helps reduce the risk of accidentally putting sensitive information into emails.

## 7. Spring Boot example: Thymeleaf + Spring Framework Mail

An application needs to send an **order confirmation email in HTML** and add a plain-text version. Goals:

- Use an HTML template located on the classpath.
- Replace recipient name and order code with **escaped text**.
- Build the URL using a trusted domain and `UUID`.
- Put the rendered HTML into a `MimeMessage` using `MimeMessageHelper`.
- Keep `From`, `To`, and `Subject` headers separate from the HTML template.

### 7.1. Dependencies

With Maven:

```xml
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
```

The Mail starter provides email-sending integration; the Thymeleaf starter provides the template engine and corresponding configuration in Spring Boot. The template engine **renders strings**, while the mail sender **builds and sends messages**.

### 7.2. SMTP configuration

Example `application.yml` for an SMTP submission server supporting STARTTLS on port 587:

```yaml
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
    from: ${MAIL_FROM_ADDRESS}
```

This is an illustrative configuration. When deploying, choose host, port, TLS, and credentials according to the provider; use a secret manager or environment variables instead of hardcoding passwords.

`spring.mail.default-encoding=UTF-8` helps handle Vietnamese characters when creating MIME text/HTML. It **does not replace HTML escaping** at the template rendering step.

### 7.3. Creating the HTML template

Place the file:

```text
src/main/resources/templates/mail/order-confirmation.html
```

Example template content:

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Order confirmation</title>
</head>
<body style="margin: 0; padding: 24px; font-family: Arial, sans-serif;">
  <main style="max-width: 600px; margin: 0 auto;">
    <h1 style="font-size: 24px; color: #1d2939;">
      Order confirmed
    </h1>

    <p>
      Hello,
      <strong th:text="${customerName}">Customer</strong>!
    </p>

    <p>
      Order
      <strong th:text="${orderCode}">ORD-EXAMPLE</strong>
      has been recorded.
    </p>

    <p>
      <a th:href="${orderUrl}"
         style="display: inline-block; padding: 12px 16px;
                background-color: #175cd3; color: #ffffff;
                text-decoration: none; border-radius: 6px;">
        View order
      </a>
    </p>

    <p style="color: #667085; font-size: 13px;">
      If you did not place this order,
      please visit the application or contact support.
    </p>
  </main>
</body>
</html>
```

Notable points:

- `th:text` is used for customer name and order code, so content is **escaped** instead of treated as markup.
- `th:href` uses a URL variable generated by the backend from a trusted domain.
- Structural CSS tags and attributes are all **written in advance by the application**.
- Sample strings between tags, such as `Customer` or `ORD-EXAMPLE`, are placeholder fallback content in the template file; when rendered by Thymeleaf, they are replaced by values from the context.
- `<meta charset="UTF-8">` is information inside HTML; the MIME text part still needs a matching charset when sent over email.

This is a simple HTML email example. Mail clients have different levels of CSS support; production layouts may need table layouts or more compatible CSS rules, yet **the principle of separating data from markup does not change**.

### 7.4. Service building HTML and sending with `JavaMailSender`

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.UUID;

@Service
public class OrderConfirmationMailService {

    private static final String ORDER_URL_PREFIX =
            "https://app.example.org/orders/";

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;
    private final String fromAddress;

    public OrderConfirmationMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
        this.fromAddress = fromAddress;
    }

    public void sendOrderConfirmation(
            String recipient,
            String customerName,
            UUID orderId,
            String orderCode
    ) throws MessagingException {

        // Fixed domain controlled by the application.
        // UUID keeps the ID part syntactically predictable.
        String orderUrl = ORDER_URL_PREFIX + orderId;

        Context context = new Context(Locale.forLanguageTag("en"));
        context.setVariable("customerName", customerName);
        context.setVariable("orderCode", orderCode);
        context.setVariable("orderUrl", orderUrl);

        // The template handles escaping itself via th:text/th:href.
        String html = templateEngine.process(
                "mail/order-confirmation", context
        );

        // Text version helps mail clients that do not display HTML.
        String plain = "Hello " + customerName + "!\n"
                + "Order " + orderCode + " has been confirmed.\n"
                + "View order: " + orderUrl;

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Order confirmation " + orderCode);
        helper.setText(plain, html);

        mailSender.send(message);
    }
}
```

The values `recipient`, `customerName`, and `orderCode` in the example are assumed to have passed appropriate business validation (length, right recipient, order code format). `orderId` is a `UUID`; the fixed URL is just an illustrative hostname, needing replacement with a trusted HTTPS domain per environment and ensuring the recipient must log in/be authorized when opening the details page.

**What keeps the boundary safe?**

1. The template engine receives `customerName` and `orderCode` as **data values**.
2. The HTML file uses `th:text`, not `th:utext`, for those dynamic fields.
3. The URL is built from an HTTPS prefix owned by the application, not accepting an arbitrary user-supplied URL.
4. `MimeMessageHelper` sets `From`, `To`, and `Subject` via dedicated APIs, without merging them into the HTML template.
5. `setText(plain, html)` creates text and HTML versions of the same content; it does not build MIME headers manually.

### 7.5. When sending multiple emails, should a Context be shared?

You should not share a mutable `Context` across parallel sending threads. Each email should create a separate context containing the right recipient's data:

```java
Context context = new Context(locale);
context.setVariable("customerName", name);
context.setVariable("orderCode", code);
```

If a context is reused and has its values overwritten while multiple emails are rendering, personalized content can leak between recipients. The Spring-managed template engine can be shared according to its contract, while **the per-request model/context must be kept separate**.

## 8. Why should there be a plain-text version?

HTML email can be rendered differently in Outlook, Gmail, mobile mail apps, or text-only clients. Some users turn off HTML or assistive tools prefer plain text.

In MIME, the two versions are usually packaged using **`multipart/alternative`**:

```text
MimeMessage
└── multipart/alternative
    ├── text/plain; charset=UTF-8
    │   └── "Hello. Order confirmed..."
    └── text/html; charset=UTF-8
        └── "<p>Hello...</p>"
```

In Spring:

```java
helper.setText(plainText, htmlText);
```

`MimeMessageHelper` will build the appropriate MIME structure when initialized in multipart mode. **Both versions must have the same business meaning**: if HTML has a link to the order, the plain-text version should have a readable and copyable URL.

### Is HTML escaping needed in plain-text?

Not in the same way. Plain-text has no HTML parser to turn `<b>` into bold text. If the content is text, the string `<b>` may appear verbatim without creating an HTML element. However, you still need to:

- Limit the length and format of fields allowed to appear.
- Handle newline characters when users are not permitted to break the notification layout.
- Avoid putting sensitive data or untrusted links into the content.
- Keep the text easy for the recipient to understand.

**HTML escaping** is the operation needed at the point of rendering into markup; **text formatting/validation** is a separate task for the plain-text version.

## 9. Templates should not own message headers

An HTML template should only produce **body content**. It is not the place to put email header fields such as `From`, `To`, `Subject`, `Reply-To`, or `Content-Type` at the MIME message level.

Do not create a template string like:

```text
From: notifications@example.org
To: customer@example.net
Subject: Order confirmation
Content-Type: text/html

<html>...</html>
```

and then treat this whole string as the body of a `MimeMessage`. If passed to `setText(...)`, the `From:`/`Subject:` lines become **message body content**, not automatically headers. On the other hand, if you assemble raw MIME completely yourself, the code must handle all syntax, charset, boundaries, and many other risks manually.

Instead:

```java
String htmlBody = templateEngine.process("mail/order-confirmation", context);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setReplyTo("support@example.org");
helper.setSubject("Order confirmation");
helper.setText(htmlBody, true);
```

Headers are managed separately by the helper/Jakarta Mail, while `htmlBody` is just the rendered body. This also helps reduce the risk of **header injection** from data containing CR/LF concatenated directly into raw message headers.

**Note:** using the helper does not replace checking recipient data and SMTP policy. You must determine valid recipients, authorized senders, and business-appropriate content.

## 10. Does a template engine prevent every kind of injection by itself?

No. `th:text` helps prevent a data variable from becoming markup **in the text context**. Yet the template engine cannot know on its own whether a URL is trusted, an attachment is safe, or a business action is authorized for the user.

See the table:

| Context | Safer approach | What still must be managed |
| --- | --- | --- |
| Text in `<p>` or `<span>` | `th:text` | Length, business content |
| Text in `title` / `alt` | The engine's attribute processor | Appropriate and non-sensitive values |
| Link in `href` | `th:href` and URL built from a trusted domain | Scheme, host, access rights, token |
| Image in `src` | Resource/CID or controlled URL | Tracking, privacy, client support |
| CSS in `style` | Fixed styles or enum selecting style | Do not allow arbitrary CSS from input |
| Externally supplied rich HTML | Sanitizer with allowlist, only then unescaped output when truly needed | Updating sanitizer policy, client compatibility |
| Subject or From | `MimeMessageHelper.setSubject/setFrom` | Syntax, sending permission, length, and input data |
| PDF/image attachment | `addAttachment(...)` / `addInline(...)` | Actual file type, bytes, download permission, size |

### Concrete example: URL properly HTML-escaped yet still wrong destination

An email has:

```html
<a th:href="${redirectUrl}">Log in to view invoice</a>
```

If `redirectUrl` is taken straight from a user's request and points to a spoofed domain, escaping the attribute does not eliminate the **phishing** risk. This is a **URL trust** bug, not an HTML syntax bug.

A better design: the button's URL is built with a trusted application domain; if there are dynamic parameters, validate the format and encode URL components; when opening the link, the server still verifies access rights.

## 11. Engines and template choices for Spring Mail

In the Java/Spring ecosystem, there are several options:

| Tool | Template style | When might it be suitable? |
| --- | --- | --- |
| **Thymeleaf** | HTML templates with attributes such as `th:text`, `th:if` | Spring applications needing easily viewable HTML templates and escaping data binding |
| **FreeMarker** | Text templates with their own directives and interpolation | Systems already using FreeMarker or having many kinds of text/HTML templates |
| **Mustache** | Logic-light templates with variables and sections | Simple emails wanting to limit logic in templates |
| **Simple custom template** | Manual string replacement | Suitable only in very narrow cases; error-prone when values need escaping |

These are alternative rendering technologies, **not SMTP sending APIs**. Regardless of which engine you choose, you still need to:

1. Clearly identify the output context and escape appropriately.
2. Do not pass untrusted HTML directly into raw/unescaped mode.
3. Validate URLs/attributes/formats separately, not relying solely on HTML escaping.
4. Use `JavaMailSender` to send the message after rendering.

For example, raw output mechanisms in some template engines can bypass default escaping. Do not switch from Thymeleaf to another engine and assume escaping rules are identical; understand the syntax and defaults of the engine in use.

## 12. HTML email is not like an ordinary web page

Mail clients differ in how they handle HTML and CSS. A template that is valid when opened in a browser may still render differently in an inbox.

Some practical points:

- Many clients restrict scripts, forms, external stylesheets, or complex CSS.
- Images loaded from the Internet may be blocked or fetched through a proxy mechanism.
- Table-based layouts and inline CSS are often used to increase compatibility.
- Have a plain-text fallback and clear action button text.
- Do not design business flows requiring users to run JavaScript directly inside the email.
- Optimize HTML size, contrast, alt text, and display on small screens.
- Use resources only from trusted domains or inline CID when needed; do not assume every client handles them the same way.

### Inline images belong to MIME, not HTML escaping

An HTML template can contain:

```html
<img src="cid:brandLogo" alt="Logo" width="120" height="40"/>
```

For the mail client to find the image, the application must create the corresponding **inline MIME part**:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("New notification");
helper.setText(htmlBody, true);

helper.addInline(
        "brandLogo",
        new org.springframework.core.io.ClassPathResource(
                "mail/logo.png"
        ),
        "image/png"
);

mailSender.send(message);
```

The `src="cid:brandLogo"` content is a fixed reference, and `addInline` attaches the image data. That is a **MIME mechanism**, different from escaping a customer name. Build the HTML body before adding inline resources following the usual `MimeMessageHelper` pattern.

## 13. Separating responsibilities between data, templates, and sending

A maintainable design can be divided into layers:

```text
Order Service
  |
  | Event "order confirmed"
  v
Mail Model Builder
  |
  | Select the right data for the recipient
  | Normalize business values
  | Build URL from trusted base URL
  v
Template Renderer
  |
  | Fixed template
  | Context-appropriate th:text/th:href
  | Rendered HTML + plain text
  v
Mail Composer
  |
  | MimeMessageHelper
  | From/To/Subject, charset, MIME multipart
  v
JavaMailSender -> SMTP
```

Advantages:

- Changing the layout does not require editing order-confirmation logic.
- Data entering the email is clearly curated.
- Trusted URLs are decided before rendering.
- The helper is the single place setting message headers and MIME.
- The template engine can be swapped with little impact on the SMTP sending layer.
- Easy to generate a plain-text version with the same semantics as the HTML version.

### Do not let the template decide access rights

For example, a template has a condition:

```html
<section th:if="${showDiscount}">
  <p>You have a special offer.</p>
</section>
```

`th:if` only decides **whether to display or not display markup**. It does not protect the API that redeems the offer. The backend must still check whether the user has permission to use the code. Do not treat hiding an HTML section as an authorization mechanism.

### Avoid putting complex business logic into the template

Do not write lots of discount calculations, order statuses, and data queries right inside template expressions. Handle them in the service and pass prepared fields:

```java
context.setVariable("discountLabel", "10% off");
context.setVariable("showDiscount", true);
```

In the template:

```html
<p th:if="${showDiscount}" th:text="${discountLabel}">
  Offer
</p>
```

When formatting currency, dates/times, and language, determine the appropriate `Locale` and prepare consistent results, avoiding making the template know deep entity structures or implicitly depend on the system time zone.

## 14. Common failure symptoms

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Email shows `&lt;p&gt;...&lt;/p&gt;` instead of an HTML paragraph | HTML was escaped at an inappropriate layer or the message was sent as `text/plain` | Check rendering and `setText(html, true)` |
| User name containing `<b>` makes text bold | Used raw output or concatenated strings directly | Use `th:text` |
| User name displays `&amp;` instead of `&` | Data was pre-escaped and then the template escaped again | Pass the original value into `th:text` |
| Button leads to an unfamiliar domain | Dynamic URL was not bound to a trusted source | Build/validate the URL in the backend |
| HTML does not look like the browser | Mail client has limited HTML/CSS support | Use compatible HTML email; include a plain version |
| Accented HTML has garbled characters | Charset across source/MIME parts is inconsistent | Use UTF-8 throughout and inspect raw MIME |
| Logo `cid:brandLogo` does not display | Missing inline part or Content-ID mismatch | Call `addInline(...)` with the right CID and media type |
| Email sends successfully yet has no text version | Called only `setText(html, true)` | Create `plain` and use `setText(plain, html)` |
| Template values are not replaced | Wrong variable name or template was not processed by engine | Check how context is populated and `process(...)` is called |
| Template rendering fails before sending | Missing template, invalid expression, mismatched data model | Handle render errors separately from SMTP errors |
| Customer A's email has customer B's info | Reused mutable context or model not isolated per email | Create a separate context per email |
| Mail has a link yet user has no permission to view | Checked URL only at render time, missing backend permission check | Authenticate/authorize when opening the link |

### Error example 1: raw HTML from a customer note

```html
<div th:utext="${customerNote}"></div>
```

If the note is user data, use `th:text` to display it as text. Only use sanitized rich HTML when the business genuinely requires it.

### Error example 2: HTML sent as text

```java
String html = templateEngine.process("mail/order-confirmation", context);
helper.setText(html, false);
```

`false` tells `MimeMessageHelper` that the body is plain text. If you want HTML:

```java
helper.setText(html, true);
```

or better, when a text version exists:

```java
helper.setText(plain, html);
```

### Error example 3: confusing HTML escaping with URL protection

```html
<a th:href="${redirectUrl}">View account</a>
```

`th:href` does not guarantee `redirectUrl` belongs to a valid domain. You must control the URL destination with server-side rules, not accept an arbitrary URL string.

### Error example 4: concatenating raw data strings into the template before rendering

```java
String template = "<p>Hello " + customerName + "</p>";
String html = templateEngine.process(template, context);
```

This approach has already mixed untrusted data into the **template source** before the engine has a chance to perform normal escaping. Moreover, depending on engine configuration, `process(...)` may treat the argument as a **template name**, not arbitrary HTML content. Use a template stored at a clear location and pass `customerName` via `Context`.

## 15. Designing URLs with tokens in email

Address verification, password reset, or invitation emails often contain links with tokens. This is a case where **markup escaping** must be clearly distinguished from **business security**.

HTML snippet example:

```html
<a th:href="${verificationUrl}">Confirm email address</a>
```

A URL containing a token needs the system to:

1. Generate the token via an appropriate mechanism, limiting scope and lifetime.
2. Build the URL from a trusted domain, properly encoding query/path components.
3. Send only to the user's address following a valid verification workflow.
4. Keep the token out of application logs or unnecessary metadata.
5. Verify the token, validity, and permissions when the user accesses the endpoint.
6. Invalidate or restrict the token according to business semantics once used.

The template engine is only responsible for placing the URL into the HTML attribute with valid syntax. It **does not create the token's security**. If input data contains a valid token yet gets inserted into a spoofed domain, escaping cannot fix this mistake either.

Similarly, a link to an order must be protected by an access check after the user opens the page, rather than relying on the order ID being hard to guess.

## 16. A maintainable template development process

With many email types, you can build a resource structure:

```text
src/main/resources/
└── templates/
    └── mail/
        ├── order-confirmation.html
        ├── invoice-ready.html
        ├── password-reset.html
        └── shared/
            └── footer.html
```

Helpful principles:

- Use meaningful template names by business event.
- Define a **model contract** for each template: which variables are present, their types, and whether values can be nullable.
- Keep logos, shared CSS, and footers in template sections managed by the application.
- Explicitly choose escape/raw output for each variable; treat user-originating values as text by default.
- Avoid having templates run database queries or call services from expressions.
- Have a plain-text version conveying the same important content.
- Handle render errors separately from SMTP errors, without treating every error in the pipeline as retryable.

### Render errors differ from send errors

```text
Mail request
    |
    v
Render template
    |
    +-- Template missing / expression error
    |      -> could not build send content yet
    |
    v
Build MimeMessage
    |
    +-- Invalid address / MIME preparation error
    |      -> message creation error
    |
    v
SMTP submission
    |
    +-- Auth / quota / network / relay policy
           -> server interaction error
```

Do not retry SMTP multiple times when the template file does not exist yet or an expression error remains unchanged. Conversely, when there is a temporary network error, you need a bounded retry strategy and business states to reduce the risk of duplicate sends. Successful rendering **does not guarantee** the email is accepted by the SMTP server or delivered to the inbox.

## 17. Self-practice scenarios

### Scenario A: customer enters a name containing HTML tags

The stored name is:

```text
<em>Buyer</em>
```

If displayed as normal data, you should use:

```html
<span th:text="${customerName}">Customer name</span>
```

**Conclusion:** the tag in the name will be rendered as text, not permitted to create additional markup.

### Scenario B: product description has the `&` character

Description:

```text
Coffee & Tea
```

There is no need to replace `&` with `&amp;` in the service if the template uses `th:text`. Pass the original string into the context and let the engine perform escaping at output.

### Scenario C: users are allowed to enter rich descriptions

The product requires supporting a few tags such as `<strong>` and `<em>`. If displayed with `th:text`, those tags become literal text; if `th:utext` is used with raw input, out-of-policy content can enter the email.

**Solution:** define an HTML allowlist policy and use an appropriately maintained sanitizer, then render the sanitized part through one clear path. If formatting is not needed, use only escaped text.

### Scenario D: link in email leads outside the company domain

An `orderUrl` field is taken directly from the payload. The template uses `th:href` yet the URL still leads to an unapproved domain.

**Conclusion:** attribute escaping only protects HTML structure; you must validate/enforce the host from the backend before rendering.

### Scenario E: notification has nice HTML yet the mail client only reads text

The email only calls:

```java
helper.setText(html, true);
```

**Solution:** add a plain-text version and call `helper.setText(plain, html)` with the helper in multipart mode. Important actionable content, especially URLs, should appear in both versions.

### Scenario F: template renders properly yet the customer sees HTML code

The engine produces the string:

```html
<p>Order confirmed.</p>
```

Yet the code calls `helper.setText(html, false)`. The mail client receives `text/plain` so it displays the tags as text.

**Solution:** declare `text/html` properly with `setText(html, true)` or use two versions. This is a **MIME content type** issue, not a template escaping issue.

### Scenario G: multiple concurrent emails mix up names

The service reuses a single `Context` and changes `customerName` before each call to the engine. When threads run in parallel, values can get mixed up if the context is shared without synchronization.

**Solution:** initialize a context/model per render; do not share mutable recipient data between requests.

## 18. Quick reference table

| Goal | Tool or rule |
| --- | --- |
| Build HTML from a template | Template engine such as Thymeleaf |
| Display data as text | `th:text` |
| Insert raw HTML | Use only for trusted/policy-sanitized markup |
| Set dynamic links | `th:href` **and** backend-controlled URL |
| Select style by status | Enum/boolean mapped to fixed CSS |
| Separate HTML from business logic | Dedicated data model, dedicated template |
| Create HTML MIME | `MimeMessageHelper.setText(html, true)` |
| Have both text and HTML | `MimeMessageHelper.setText(plain, html)` in multipart mode |
| Set Subject, To, From | Dedicated APIs of `MimeMessageHelper` |
| Send email | `JavaMailSender.send(...)` |
| Display Vietnamese accurately | Consistent UTF-8 charset from source to MIME |
| Protect linked data | Backend validation of URL, token, and access rights |
| Prevent confusing data with HTML | Context-aware escaping and no raw HTML concatenation |

## 19. Conclusion

Template engines help write structured and maintainable HTML email. Yet their greatest value is not just “substituting variables in strings”: **they help the application keep the boundary between data and markup**, provided we use the right escaped-output mechanism and control special contexts such as URLs, attributes, and CSS.

In Spring Framework Mail, let the **template engine render the body**, **`MimeMessageHelper` build the MIME and message headers**, and **`JavaMailSender` send over SMTP**. User data should go through `th:text` or an equivalent escaping mechanism; raw HTML is used only when there is an allowance policy and appropriate sanitization. Even an escaped URL must still have its destination and access rights checked. When responsibilities are clearly separated, HTML email stays flexible in presentation while reducing the risk of markup injection, data mix-ups, and information leaks.
