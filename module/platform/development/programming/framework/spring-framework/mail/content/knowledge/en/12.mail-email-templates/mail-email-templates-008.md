# Controlling Expressions and Input Data

A Spring application sending order confirmation emails typically uses an HTML template to present the customer's name, order code, status, and a link to view details. The template may contain **expressions** to read values from application data, such as Thymeleaf using `${customerName}` to read the `customerName` variable. These expressions make templates reusable, yet they also create a boundary that must be controlled: **the template defines how data is interpreted, while input data must never turn into expression code or template structure**.

If an application concatenates user data directly into the template source, lets users choose arbitrary templates, or feeds unvalidated content into evaluated expressions, it can cause rendering errors, data leaks, or unintended expression execution. Even when the template is static, dynamic data still needs business validation and output in the right HTML context.

In **Spring Framework Mail**, `MimeMessageHelper.setText(html, true)` sets the email content as HTML. It **does not control template engine expressions, does not validate input data, and does not automatically sanitize HTML**. This article focuses on managing expressions and data when rendering email templates, using examples with **Thymeleaf, Spring Boot, and JavaMailSender**.

## 1. What Is an Expression in an Email Template?

An email template is a content pattern with static parts and parts that vary per send. Example:

~~~html
<h2>Order Confirmed</h2>
<p>Hello, <span th:text="${customerName}">Customer name</span>!</p>
<p>Order code: <span th:text="${orderCode}">A102</span></p>
~~~

The `th:text` attributes and `${customerName}`, `${orderCode}` expressions are Thymeleaf syntax. During rendering, the template engine reads variables from the context, substitutes the corresponding content, and produces the final HTML.

**An expression is not input data.** An expression is part of the template language, defined by the template author to retrieve or format data. The customer name and order code are data values that the expression reads.

~~~mermaid
flowchart LR
    A["Fixed template"] --> C["Template engine"]
    B["Validated input data"] --> C
    C --> D["Rendered HTML"]
    D --> E["MimeMessageHelper"]
    E --> F["JavaMailSender"]
~~~

A secure design keeps the two flows separate:

- **Template source**: managed, reviewed, and deployed by the application alongside the software release.
- **Template context**: holds per-email data, validated before rendering.

During rendering, the engine combines both parts. User data enters the context as values and must never be used to construct expressions or alter the template source.

## 2. Common Expression Types in Thymeleaf

Thymeleaf Standard Dialect and Spring integration provide several expression groups. Understanding them properly helps identify where data comes from and what operation the template is performing.

| Syntax | Name | Common Purpose |
| --- | --- | --- |
| `${...}` | Variable expression | Read variables from context, such as customer name or order code. |
| `*{...}` | Selection expression | Read properties from the currently selected object via `th:object`. |
| `#{...}` | Message expression | Fetch messages from a message source, commonly used for multi-language content. |
| `@{...}` | Link URL expression | Build URLs using Thymeleaf's URL mechanism. |
| `~{...}` | Fragment expression | Reference a template fragment to reuse content. |
| `__...__` | Expression preprocessing | Preprocess an expression before parsing the outer expression. |

Example:

~~~html
<p th:text="${customerName}">Customer name</p>

<div th:object="${order}">
  <p th:text="*{code}">A102</p>
  <p th:text="*{statusLabel}">Confirmed</p>
</div>

<p th:text="#{mail.order.confirmed}">Order has been confirmed</p>

<a th:href="@{/orders/{id}(id=${orderId})}">View order</a>
~~~

The expressions above are **code defined by the template author**. Data is passed in as `customerName`, `order`, and `orderId`. Users do not need to know expression syntax and must never be allowed to modify it through form fields.

### 2.1. Variable expression

`${...}` reads a variable or property from the context:

~~~html
<p th:text="${customerName}">Customer name</p>
~~~

If the context has `customerName` set to `Alice Nguyen`, the element displays that value. With Spring integration, expressions can be evaluated via Spring's expression mechanism. Therefore, never turn user data into an arbitrary expression and ask the engine to evaluate it.

### 2.2. Selection expression

`*{...}` is commonly used when an element or template region has selected an object:

~~~html
<section th:object="${order}">
  <p>Code: <span th:text="*{code}">A102</span></p>
  <p>Status: <span th:text="*{statusLabel}">Confirmed</span></p>
</section>
~~~

`th:object` specifies the selected object; `*{code}` accesses that object's property. This style keeps templates readable when multiple properties belong to the same object.

### 2.3. Message expression

`#{...}` retrieves content managed in a message bundle:

~~~html
<h2 th:text="#{mail.order.title}">Order notification</h2>
~~~

The application can have locale-specific message files to display Vietnamese, English, or other languages. Users should not be allowed to pick arbitrary message keys; templates should reference predefined keys.

### 2.4. URL expression

`@{...}` assists in building URLs using Thymeleaf's mechanism:

~~~html
<a th:href="@{/orders/{id}(id=${orderId})}">
  View order
</a>
~~~

In emails, links usually must be absolute URLs because readers open messages outside the website. The application must ensure the context or URL data is configured properly, uses a trusted domain, and never lets arbitrary input decide scheme/host.

### 2.5. Fragment expression

Templates can reuse headers/footers:

~~~html
<div th:replace="~{mail/fragments :: footer}"></div>
~~~

Template and fragment names should be controlled choices made by the application. Never concatenate a fragment name from a user request and pass it into an expression for the engine to locate and render arbitrary content.

### 2.6. Expression preprocessing

Preprocessing syntax allows an inner expression to be evaluated before the outer expression is parsed. This is useful for some advanced templates, yet **preprocessing content must never be built from user data**. It increases evaluation complexity and can open a path for data to become syntax.

In ordinary emails, use explicit context variables and fixed expressions; use preprocessing only when there is a specific, fully understood, and controlled template requirement.

## 3. Trust Boundary: Template Source vs. Template Data

An email template typically contains:

- HTML markup managed by the development team.
- Thymeleaf expressions written by the template author.
- Static content such as headings, instructions, and footers.
- Placeholders reading dynamic data from context.

Trusted template example:

~~~html
<h2>Order Confirmed</h2>
<p>Hello, <span th:text="${customerName}">Customer</span>!</p>
<p>Order code: <span th:text="${orderCode}">A102</span></p>
~~~

Untrusted data:

~~~text
customerName = "An <Bao>"
orderCode = "A102"
~~~

When rendered, `th:text` treats the name as text and escapes HTML appropriately. The recipient sees `An <Bao>` as text; `<Bao>` does not become a new tag.

**Do not do the following:**

~~~java
String template = "<p>Hello, " + userInput + "!</p>";
// Then pass this dynamic content through an engine to process as a template.
~~~

This mixes data into the template source. If the user enters markup or template syntax, the engine or HTML reader may interpret the content unexpectedly.

A better approach is keeping the template fixed and passing data via context:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("customerName", userInput);

String html = templateEngine.process(
        "mail/welcome",
        context
);
~~~

The `mail/welcome` template is managed by the application; `userInput` is merely a variable value. Using context does not validate business data by itself, yet it keeps the boundary between source and data clear.

## 4. Expression Injection and Template Injection

These two concepts are related but not identical.

**Expression injection** occurs when untrusted input can influence an evaluated expression. For example, an application concatenates a user string into a Spring Expression Language expression and then parses/evaluates it. A user could cause the system to evaluate unintended content.

**Template injection** occurs when a user can control part or all of the template source, and the application then feeds that source to the template engine for rendering. If the template engine supports expressions, user-supplied content can be processed as syntax instead of text.

Illustrative design flaw at the expression layer:

~~~java
// Do not do this: userInput is used to build expression source.
String expressionText = "${" + userInput + "}";

// Parsing/evaluating arbitrary expressions from input is risky.
~~~

Illustrative design flaw at the template layer:

~~~text
User enters template or markup
        ↓
Application stores content as template source
        ↓
Template engine evaluates expressions inside
        ↓
Content is rendered with the engine's privileges
~~~

Not every string containing `${...}` is automatically executed. Risk arises when that string enters **the template source or expression parser** in a way that makes the engine evaluate it. If the string is merely passed as a variable and output via `th:text`, it is treated as text data.

### Why Is This Risk Worth Addressing?

Depending on the template engine, dialect, version, and evaluation context configuration, expressions can access variables, properties, methods, or beans exposed within the evaluation scope. If the template source is untrusted, the engine's capabilities can go far beyond substituting a simple placeholder.

Never assume a template engine is a sandbox for running user-submitted templates. Treat **template source and expressions as application code**, applying access control, review, and release processes just as for code.

## 5. Passing Data into Context Instead of Building Dynamic Expressions

The recommended design is: the template defines fixed expressions; Java prepares an object with required data and adds it to the context.

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));

context.setVariable("customerName", customerName);
context.setVariable("orderCode", orderCode);
context.setVariable("statusLabel", statusLabel);
~~~

Template:

~~~html
<p>Hello, <span th:text="${customerName}">Customer</span>!</p>
<p>Order code: <span th:text="${orderCode}">A102</span></p>
<p>Status: <span th:text="${statusLabel}">Confirmed</span></p>
~~~

There is no need to build expressions from a field name sent by the user. For example, avoid accepting a request with `fieldName` and building an expression string from it to read arbitrary object properties.

### Use Small DTOs Instead of Passing Entire Domain Objects into Templates

Do not pass a large domain object containing many relationships and methods if the template only needs a few values. A more controllable option:

~~~java
public record OrderMailView(
        String orderCode,
        String customerName,
        String statusLabel,
        String detailsUrl) {
}
~~~

Create a view model containing only the fields the template is allowed to display:

~~~java
OrderMailView view = new OrderMailView(
        order.getCode(),
        customer.getDisplayName(),
        statusLabel,
        detailsUrl
);

context.setVariable("mail", view);
~~~

Template:

~~~html
<p th:text="${mail.customerName}">Customer</p>
<p th:text="${mail.orderCode}">A102</p>
<p th:text="${mail.statusLabel}">Confirmed</p>
<a th:href="${mail.detailsUrl}">View order</a>
~~~

DTOs limit the data passed into the template and clarify the contract between the rendering service and the template. However, using a DTO does not replace data validation, authorization, or URL checks.

## 6. Controlling Input According to Business Rules

Not all data needs the same validation. An order code, email address, customer name, and free-form note have different rules.

| Field | Input Check Example |
| --- | --- |
| Recipient address | Non-empty, valid email syntax, recipient allowed to receive this notification type. |
| Order code | Matches system-defined format, length-limited. |
| Customer name | Required or optional per business rules, length-limited; still allows Unicode and valid name characters. |
| Order status | Accepts only a value from an enum/allowlist. |
| Note | Length-limited, newlines allowed if needed; treated as text when rendered. |
| Locale | Selected from supported locale list. |
| Template name | Selected from a fixed list of templates managed by the application. |
| URL | Built from a trusted host or validated for scheme/host/path per policy. |

**Validation and escaping are two distinct steps:**

- Validation determines whether data satisfies the business contract.
- Escaping/encoding represents data properly for the output context.
- Authorization determines whether a user has permission to send a notification or view related data.

A customer name containing `<` may be valid as text; it does not necessarily have to be rejected. Instead, HTML output must escape that character when placing it into a text node.

### 6.1. Validating Data with Bean Validation

Example DTO receiving a send request:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record OrderMailRequest(
        @NotBlank
        @Email
        String recipient,

        @NotBlank
        @Size(max = 120)
        String customerName,

        @NotBlank
        @Pattern(regexp = "[A-Z0-9-]{1,32}")
        String orderCode,

        @Size(max = 500)
        String customerNote
) {
}
~~~

Validation can be triggered at the controller/service layer using `@Valid` or by calling a validator according to the application architecture. Controller example:

~~~java
@PostMapping("/mail/order-confirmation")
public ResponseEntity<Void> send(
        @Valid @RequestBody OrderMailRequest request) {

    orderMailService.sendConfirmation(request);
    return ResponseEntity.accepted().build();
}
~~~

This is an illustrative example when the application has Spring Web and Bean Validation. `@Email` validates format at the validator level, not whether the mailbox exists. `@Size` limits length, without replacing output escaping. `@Pattern` is only appropriate for order codes with an actual pattern like the example; do not use overly strict regexes for real people's names.

### 6.2. Do Not Validate by Stripping Special Characters

Avoid handling customer names by stripping every `<`, `>`, or `&`. That alters valid data. Keep strings according to business rules and escape at HTML locations. If business rules forbid certain control characters or restrict Unicode, state those rules explicitly and validate at input.

### 6.3. Deliberate Data Normalization

Trimming leading/trailing whitespace or uppercasing order codes may be necessary. However, do not automatically mutate every user string without understanding its meaning, as that can alter names, languages, or note content.

A sensible pipeline:

1. Define rules for the field.
2. Normalize what the rules permit.
3. Validate the normalized value.
4. Keep the logical value for business use.
5. Encode/escape when outputting to the template.

## 7. Selecting Templates via Allowlist, Not Arbitrary Names

An application may have templates:

~~~text
mail/order-confirmed.html
mail/payment-received.html
mail/password-reset.html
~~~

Do not take `templateName` directly from a request and pass it to the template engine. If the template resolver can look up templates by dynamic name, callers might select unintended content or exploit how the resolver is configured.

Instead, use an enum or allowlist:

~~~java
public enum MailTemplate {
    ORDER_CONFIRMED("mail/order-confirmed"),
    PAYMENT_RECEIVED("mail/payment-received"),
    PASSWORD_RESET("mail/password-reset");

    private final String templateName;

    MailTemplate(String templateName) {
        this.templateName = templateName;
    }

    public String templateName() {
        return templateName;
    }
}
~~~

Then the service selects the template via a validated business decision:

~~~java
String templateName = switch (mailType) {
    case ORDER_CONFIRMED -> MailTemplate.ORDER_CONFIRMED.templateName();
    case PAYMENT_RECEIVED -> MailTemplate.PAYMENT_RECEIVED.templateName();
    case PASSWORD_RESET -> MailTemplate.PASSWORD_RESET.templateName();
};

String html = templateEngine.process(templateName, context);
~~~

`mailType` should be an enum or a value mapped through an allowlist, not a free-form path supplied by the user.

**Do not allow requests to pick arbitrary template files**, such as passing an arbitrary path or resource name and expecting the resolver to protect itself. Fix template names in code or trusted administrative configuration.

## 8. Do Not Use User Data to Decide Expressions or Fragments

Templates can have multiple variants:

~~~html
<div th:replace="~{mail/fragments :: footer}"></div>
~~~

This is a fixed fragment selection. If the application builds fragment names from input, data can affect template structure or the content loaded.

If the product needs users to choose a footer type, theme, or language, use an **allowlist selection code**:

~~~java
String footerFragment = switch (theme) {
    case STANDARD -> "mail/fragments :: standardFooter";
    case COMPACT -> "mail/fragments :: compactFooter";
};
~~~

The options are constants defined by the application. Users only choose an allowed business value, never providing fragment or expression syntax.

Similarly, do not construct variable names, properties, or method calls inside expressions based on input strings. Put the required variables into the context under fixed names.

## 9. th:text and th:utext: Controlling Output Data

A safe email template typically uses `th:text` for text data:

~~~html
<p th:text="${customerName}">Customer name</p>
<p th:text="${customerNote}">Note</p>
~~~

`th:text` inserts the value as text content and performs HTML escaping. Data `An <Bao> & Co.` will be represented safely so readers still see the exact name.

Conversely:

~~~html
<p th:utext="${customerNote}">Note</p>
~~~

`th:utext` outputs unescaped content. If notes are free-form strings, do not use this approach. The data could contain markup or structure the template did not intend to allow.

### When Is Rich Text Needed?

If business rules allow users to write formatted content such as bold text, lists, and links, full HTML escaping will display tags as text. In that case, an **allowlist-based HTML sanitizer** is required before putting controlled content into an unescaped region.

The allowlist must clearly specify:

- Which tags are allowed, e.g., `p`, `strong`, `em`, `ul`, `li`.
- Which attributes are allowed.
- Whether `href` is allowed and which schemes are accepted.
- Whether images, CSS, or remote resources are allowed.
- How nested tags and invalid markup are handled.

Do not write your own sanitizer using a couple of regexes. HTML has complex parsing rules; use a maintained library, configure clear policies, and verify output before rendering.

## 10. URL Expressions and Input Data

Emails often have links like "View order", "Reset password", or "Track request". Templates can use URL expressions:

~~~html
<a th:href="@{/orders/{id}(id=${orderId})}">
  View order
</a>
~~~

In emails, URLs should be **absolute addresses** that recipients can open from outside the application. You can pass a URL built from trusted configuration into the context:

~~~html
<a th:href="${detailsUrl}">View details</a>
~~~

Yet the template escaping the attribute value does not by itself verify that the URL is safe. The application must:

1. Use an HTTPS base URL configured by the system.
2. Build path/query from validated data and properly encode components.
3. Never let input decide host or scheme.
4. Not put secret tokens into URLs if product policy forbids it.
5. If the URL comes from an external source, check domain/scheme allowlists and redirect rules.

For example, an order code can be restricted to `[A-Z0-9-]{1,32}` and placed into an encoded path segment. The host still comes from application configuration, not from a Host header or user-entered string without a verification mechanism.

### Expressions Do Not Replace URL Validation

`@{...}` helps build URLs per Thymeleaf rules, but does not know whether a URL respects business access permissions. A template can render a syntactically valid link pointing to an order that does not belong to the recipient. **Authorization and user-resource relationship checks must be performed before rendering.**

## 11. Limiting Data Placed into the Template Context

A concise, strongly typed context reduces confusion. Example:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));

context.setVariable("mail", new OrderMailView(
        orderCode,
        customerName,
        statusLabel,
        detailsUrl
));
~~~

Avoid putting into the context:

- The entire Spring ApplicationContext or bean registry.
- Services capable of performing write/delete operations or system access.
- Large entities containing lazy-loaded relationships and unrelated data.
- Request/session objects with many sensitive attributes.
- Objects containing credentials, tokens, or secrets unnecessary for the template.

Templates should receive only **minimal display data**. Passing minimal data does not create a complete sandbox for expressions on its own, yet it reduces the chance of templates accessing unintended data and keeps the contract easy to review.

### Use Specific Data Types

Instead of an arbitrary map holding dozens of keys, you can create a DTO:

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        boolean paid,
        String detailsUrl) {
}
~~~

DTOs enable compiler structural checks, clarify which fields the template needs, and prevent passing the wrong object. Even so, inner values must still be validated and output in the right context.

## 12. Limiting Loops and Collection Data

Email templates can loop over a list of products:

~~~html
<tr th:each="item : ${mail.items}">
  <td th:text="${item.name}">Product</td>
  <td th:text="${item.quantity}">1</td>
</tr>
~~~

The `th:each` expression is written statically in the template; the `mail.items` collection is data passed into the context. Never let users submit an arbitrary expression to decide the collection or how properties are accessed.

Before rendering, control:

- Maximum item count to avoid overly long emails or excessive resource consumption.
- Data types and required fields of each item.
- Numeric values such as quantity, price, and total per business rules.
- Permissions verifying items belong to the right order/recipient.
- How the template renders when the collection is empty.

Limit example:

~~~java
if (items == null || items.size() > 100) {
    throw new IllegalArgumentException(
            "Invalid product list"
    );
}
~~~

The number 100 is merely illustrative; the real limit must be based on email design, rendering performance, and provider size limits.

Do not let templates perform critical business calculations such as computing the final total. Compute and validate at the domain/service layer, then pass the finalized value into the view model.

## 13. Expressions in Message Bundles and Multi-Language Content

Emails often need a locale per recipient. Thymeleaf can use message expressions:

~~~html
<h2 th:text="#{mail.order.title}">Order notification</h2>
<p th:text="#{mail.order.greeting(${mail.customerName})}">
  Hello
</p>
~~~

Message keys should be managed in resource bundles:

~~~properties
mail.order.title=Đơn hàng đã được xác nhận
mail.order.greeting=Xin chào, {0}!
~~~

English example in a separate resource:

~~~properties
mail.order.title=Your order is confirmed
mail.order.greeting=Hello, {0}!
~~~

The application selects a validated locale:

~~~java
Locale locale = switch (requestedLanguage) {
    case "vi" -> Locale.forLanguageTag("vi-VN");
    case "en" -> Locale.US;
    default -> Locale.forLanguageTag("vi-VN");
};

Context context = new Context(locale);
~~~

Do not take an arbitrary locale string directly and assume the system has a corresponding message bundle. Pick a locale from the supported list while keeping data passed into message parameters as values. Message bundles are application-managed content; never let users supply arbitrary message key expressions.

## 14. Complete Example: Validate Input, Render Template, and Send Mail

The example below illustrates the boundary between request, display data, template, and Spring Mail.

### 14.1. Input DTO

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record OrderConfirmationRequest(
        @NotBlank
        @Email
        String recipient,

        @NotBlank
        @Size(max = 120)
        String customerName,

        @NotBlank
        @Pattern(regexp = "[A-Z0-9-]{1,32}")
        String orderCode,

        @Size(max = 500)
        String note
) {
}
~~~

The `orderCode` format is an example; the system must replace it with real order-code rules. Names and notes are not banned from containing `<` or `&` merely because they appear in HTML; the template treats them as text.

### 14.2. View Model for the Template

~~~java
public record OrderMailView(
        String customerName,
        String orderCode,
        String statusLabel,
        String note,
        String detailsUrl) {
}
~~~

The view model contains only display data. Do not pass SMTP credentials, full entities, or services into the context.

### 14.3. Fixed Thymeleaf Template

File `src/main/resources/templates/mail/order-confirmed.html`:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Order Confirmed</title>
</head>
<body>
  <h2>Order Confirmed</h2>

  <p>
    Hello,
    <strong th:text="${mail.customerName}">Customer</strong>!
  </p>

  <p>
    Order code:
    <span th:text="${mail.orderCode}">A102</span>
  </p>

  <p>
    Status:
    <span th:text="${mail.statusLabel}">Confirmed</span>
  </p>

  <p th:if="${mail.note != null and !#strings.isEmpty(mail.note)}">
    Note:
    <span th:text="${mail.note}">Note</span>
  </p>

  <p>
    <a th:href="${mail.detailsUrl}">View order details</a>
  </p>
</body>
</html>
~~~

The expressions are constants written by developers. `th:text` escapes displayed content; `th:if` decides whether to render the note section based on a context variable. `th:href` sets the URL on the attribute; the application must still build and validate the URL beforehand.

### 14.4. Rendering and Sending Service

~~~java
import java.net.URI;
import java.util.Locale;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class OrderConfirmationMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine templateEngine;
    private final String fromAddress;
    private final URI publicBaseUri;

    public OrderConfirmationMailService(
            JavaMailSender mailSender,
            TemplateEngine templateEngine,
            @Value("${app.mail.from}") String fromAddress,
            @Value("${app.public-base-url}") URI publicBaseUri) {

        this.mailSender = mailSender;
        this.templateEngine = templateEngine;
        this.fromAddress = fromAddress;
        this.publicBaseUri = publicBaseUri;
    }

    public void send(OrderConfirmationRequest request)
            throws MessagingException {

        // Data was already validated at the application boundary.
        String name = request.customerName().trim();
        String code = request.orderCode();

        // Status is taken from the business outcome, not from arbitrary input.
        String statusLabel = "Confirmed";

        // Base URI comes from trusted configuration; code uses an allowlist.
        String detailsUrl = buildDetailsUrl(publicBaseUri, code);

        OrderMailView view = new OrderMailView(
                name,
                code,
                statusLabel,
                request.note(),
                detailsUrl
        );

        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("mail", view);

        // Template name is an application-managed constant.
        String html = templateEngine.process(
                "mail/order-confirmed",
                context
        );

        String plainText = """
                Hello, %s!

                Order %s has been confirmed.
                Status: %s

                View details: %s
                """.formatted(name, code, statusLabel, detailsUrl);

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom(fromAddress);
        helper.setTo(request.recipient());
        helper.setSubject("Order " + code + " has been confirmed");
        helper.setText(plainText, html);

        mailSender.send(message);
    }

    private static String buildDetailsUrl(URI baseUri, String orderCode) {
        if (!"https".equalsIgnoreCase(baseUri.getScheme())
                || baseUri.getHost() == null
                || baseUri.getUserInfo() != null) {
            throw new IllegalArgumentException(
                    "Invalid application base URL"
            );
        }

        // orderCode was validated against an allowlist at the request layer.
        String base = baseUri.toString().replaceAll("/+$", "");
        return base + "/orders/" + orderCode;
    }
}
~~~

`buildDetailsUrl` is kept simple because the order code was restricted to uppercase letters, digits, and hyphens. If path segments can contain other characters, use a URI builder and properly URL-encode path segments; never concatenate strings arbitrarily. In a real system, also ensure `publicBaseUri` comes from trusted configuration and allows only managed domains.

The example focuses on preparing the template and message. Actual sending also depends on SMTP configuration, permission to use `From`, recipient policies, and `MailException` error handling.

### 14.5. What Was Protected Where?

| Component | Where Controlled | Mechanism |
| --- | --- | --- |
| Recipient address | DTO / service | Bean Validation and authorization |
| Order code | DTO / domain | Format allowlist |
| Name and note | Template output | `th:text` HTML escaping |
| Template name | Application code | Constants/allowlist |
| Expressions | Template file | Application-managed template source |
| URL | Service / configuration | Trusted HTTPS base, host and path checks |
| SMTP credentials | Deployment configuration | Secret/environment management |
| MIME message | Spring Mail/Jakarta Mail | `MimeMessageHelper` |
| Send connection | JavaMailSender | SMTP, TLS, and AUTH per configuration |

No single annotation or `validate()` method does all of the above. Each boundary needs its appropriate mechanism.

## 15. What If Users Are Allowed to Create Templates?

Some products allow administrators or tenants to edit email templates themselves. In that case, templates are no longer purely developer-controlled code. The degree of freedom granted must be decided explicitly.

### Level 1: Allow Static Text Updates Only

Allow users to edit headings or paragraphs, without letting them enter expressions. Content is output as text or through an editor with explicit rules.

### Level 2: Allow an Allowlisted Placeholder Set

For example, support only:

~~~text
{{customerName}}
{{orderCode}}
{{supportUrl}}
~~~

The application substitutes placeholders from a fixed list of variable names. Do not allow placeholders to contain expressions, method calls, bean references, or arbitrary syntax. Substituted values must be escaped according to HTML position, and the parser must handle placeholders explicitly instead of evaluating them as Spring EL.

### Level 3: Allow Restricted Rich HTML

If users are allowed to edit markup, use an HTML sanitizer with a tag/attribute/URL allowlist. Thymeleaf expressions should be forbidden or never evaluated in user-supplied sources.

### Level 4: Allow Advanced Template Expressions

This carries higher risk. It requires a dedicated design: a restricted template language, minimal evaluation context, controlled view model data, render time/size limits, tenant isolation, and security review. Do not simply let users submit any Thymeleaf template and render it with the same engine that has access to the application's application context.

**Do not treat an HTML sanitizer as an expression sandbox.** A filter that strips script tags does not necessarily understand or strip every template syntax. Handle both languages at their respective layers.

## 16. Controlling Template Name, Locale, and Expression Content

Besides text data, several values can unintentionally control rendering:

| Value | Risk If Uncontrolled | Approach |
| --- | --- | --- |
| Template name | Selecting unintended template or exploiting resolver | Enum/allowlist in code |
| Fragment name | Selecting disallowed fragment | Constants or approved choice map |
| Locale | Requesting unsupported bundle, unexpected fallback | Locale allowlist |
| Expression string | Evaluating user-controlled syntax | Never parse/evaluate expressions from input |
| Collection for `th:each` | Rendering too many rows, consuming memory | Limit size and data types |
| URL | Spoofed links or unexpected destination | Trusted base URL, scheme/host checks |
| Rich HTML text | Disallowed markup or attributes | Allowlist sanitizer or display as text |

If the template has conditionals:

~~~html
<div th:if="${mail.paid}">
  Order has been paid.
</div>
~~~

`mail.paid` should be a boolean computed from business results, not an unvalidated `"true"` string submitted by a user. Templates express presentation; they are not where payment completion is determined.

Similarly, do not use expressions to recompute monetary amounts, access permissions, or order status. Those decisions must come from an authoritative domain/service.

## 17. Checking Render Output Before Sending

When templates have many variables and conditions, have dedicated render tests to catch expression errors and data errors before connecting to SMTP.

For example, with test data:

~~~java
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("mail", new OrderMailView(
        "An <Bao> & Co.",
        "A102",
        "Confirmed",
        "Call before 17:00 & ask reception",
        "https://app.example.org/orders/A102"
));

String html = templateEngine.process(
        "mail/order-confirmed",
        context
);
~~~

You can verify the output contains the escaped display content, such as `An &lt;Bao&gt; &amp; Co.`, rather than asserting one specific raw expression string. Also check:

- The template is found and renders without throwing errors.
- Required variables are supplied.
- Conditional branches and lists with empty data behave reasonably.
- Links are generated from the expected domain.
- Data with special characters does not create unintended markup.
- The plain-text version keeps logical text without containing HTML entities.
- Content and item counts stay within application limits.

### Test Payloads in Test Environments

Some strings that can verify text-node escaping:

~~~text
An <Bao> & Co.
"VIP" and 'customer'
<p>This is a note</p>
5 < 10 & 10 > 5
~~~

When passed into `th:text`, characters with HTML meaning must be represented as text. This test verifies **render output**, without needing to send real emails.

There is no need to use complex exploit payloads in production data. Controlled tests verify the template/data boundary without exposing customer information.

### Do Not Log Full Context

Context can contain names, email addresses, order codes, URLs with tokens, and private notes. When template rendering fails, logs should record template name, request ID, error type, and minimal metadata. Do not dump the full context or raw HTML into production logs without an appropriate protection policy.

## 18. Common Mistakes

### 18.1. Concatenating User Data into Template Source

**Mistake:** users can alter the markup or expressions processed by the engine.

**Practice:** keep the template fixed, pass data through context, and use escaped output.

### 18.2. Feeding User-Entered Expressions into a Parser

**Mistake:** input strings become evaluated expressions.

**Practice:** never parse/evaluate expressions from requests. Use variables and allowlist selections.

### 18.3. Letting Users Select Templates via Arbitrary Paths

**Mistake:** the template resolver may locate content outside the expected list, depending on resolver configuration.

**Practice:** map business codes to fixed template names.

### 18.4. Using th:utext for Free-Form Notes

**Mistake:** data may be interpreted as markup.

**Practice:** use `th:text`; if rich HTML is needed, sanitize with an allowlist.

### 18.5. Putting Entire Entities or Services into Context

**Mistake:** templates may see more attributes/methods than needed, expanding data scope and access capability.

**Practice:** create a DTO/view model with only fields permitted for display.

### 18.6. Confusing Validation with Escaping

**Mistake:** checking that a name is non-empty yet concatenating it directly into HTML.

**Practice:** validate per business rules, then escape according to output context.

### 18.7. Escaping All Data When Saving to the Database

**Mistake:** data becomes tied to HTML context, potentially showing entities in plain text or causing double escaping.

**Practice:** store logical data and escape when rendering HTML.

### 18.8. Letting Input URLs Decide the Host

**Mistake:** links in emails may point to unauthorized hosts.

**Practice:** use a trusted base URL, validate scheme/host, and encode path/query components.

### 18.9. Using Templates to Compute Business Decisions

**Mistake:** expressions display payment status or access permissions based on unvalidated data.

**Practice:** compute decisions in services/domain and pass explicit results into the view model.

### 18.10. Thinking MimeMessageHelper Handles Template Security Automatically

**Mistake:** the helper only builds MIME content; it does not know which expressions are allowed or which data is trusted.

**Practice:** process templates and input before calling `setText(...)`.

## 19. Reasoning Exercises

**Question 1.** A template has `th:text="${customerName}"` and the context contains `An <Bao>`. Do you need to escape the name manually before putting it into the context?

Usually **no**, if the template uses escaped output `th:text`. Pass the logical data string and let the template escape at the output point. Avoid escaping twice.

**Question 2.** A request sends `${T(...)}`. If the application simply puts that string into a variable and displays it with `th:text`, will it automatically evaluate as an expression?

No. In that case, the string is a data value output as text. Risk appears if the application puts the string into the template source or an expression parser for evaluation.

**Question 3.** Can clients pass `templateName` and then call `templateEngine.process(templateName, context)`?

Do not accept arbitrary template names from clients. Map an allowed business template code to a fixed name.

**Question 4.** Why should the entire `OrderEntity` not be placed into the context?

An entity can hold many relationships, sensitive data, and methods unnecessary for email. A small DTO/view model restricts data and clarifies the template contract.

**Question 5.** Can `th:utext` be used for user notes if a simple HTML escape function has already been called?

If it is already fully escaped, the goal of preserving rich HTML is lost; if not escaped/sanitized, content can become unintended markup. For text notes, use `th:text`. For rich HTML, use an appropriate allowlist sanitizer before unescaped output.

**Question 6.** Does `@{...}` guarantee links are not spoofed?

No. It builds URLs per Thymeleaf's mechanism, yet the application must still control the base URL, scheme, host, and resource access permissions.

**Question 7.** A template uses `th:each` on a list of 10,000 products. Does the list need a limit?

Yes. Limit item count, data size, and email content to avoid overly large renders, exceeding provider limits, or exhausting resources.

**Question 8.** Does `MimeMessageHelper.setText(html, true)` prevent expression injection?

No. Expression injection belongs to the template/evaluation layer. The helper only sets the rendered string or prepared HTML as the MIME body.

## 20. Mental Model to Remember

A secure email template must control **three boundaries**:

~~~mermaid
flowchart TD
    A["Request / data from external systems"] --> B["Validation + authorization"]
    B --> C["Minimal DTO / view model"]
    D["Fixed, reviewed template source"] --> E["Template engine"]
    C --> E
    E --> F["HTML render: escaped output"]
    F --> G["MimeMessageHelper"]
    G --> H["JavaMailSender / SMTP"]
~~~

Remember these principles:

1. **Expressions are template syntax; input data is values.** Never turn user strings into expressions or template sources.
2. **Keep template sources under application control.** Template names, fragments, locales, and template choices must go through allowlists.
3. **Pass data via context and small DTOs.** Put only fields actually needed for display into templates.
4. **Validate per business rules before rendering.** Check addresses, codes, sizes, statuses, and permissions; do not strip special characters arbitrarily.
5. **Use escaped output for text.** In Thymeleaf, `th:text` suits text data; `th:utext` is only for controlled/sanitized HTML.
6. **Control URLs independently.** URL expressions and HTML attribute escaping do not replace scheme, host, or access-permission checks.
7. **Limit collections and context data.** Templates should only present prepared data, never make critical business decisions on their own.
8. **Test rendering before sending.** Verify HTML/plain-text outputs and handle template errors separately from SMTP errors.
9. **Do not treat a template engine as a sandbox for untrusted templates.** If users must customize templates, design a restricted language and separate isolation mechanism.

In Spring Framework Mail, the application should finish input validation and template rendering before calling `MimeMessageHelper.setText(...)`. Thymeleaf handles evaluating fixed expressions and outputting data per template rules; `MimeMessageHelper` packages the content into MIME; `JavaMailSender` sends the message over SMTP. When the boundaries between **expressions, template sources, and input data** remain clear, emails can be personalized while keeping content and exposed data scope under control.
